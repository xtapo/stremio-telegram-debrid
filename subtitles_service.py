import os
import re
import base64
import httpx
import urllib.parse
import asyncio
import logging
import subprocess
from typing import Optional
from config import Config

# Parsing / timing / translation helpers live in subtitle_utils.py and are re-exported
# here so every existing "from subtitles_service import ..." keeps working.
from subtitle_utils import (
    CACHE_DIR,
    GOOGLE_TRANSLATE_ENDPOINT,
    GEMINI_API_BASE,
    OPENSUBTITLES_BASE,
    SUBTITLE_TIME_OFFSET,
    TEXT_SUB_CODECS,
    IMAGE_SUB_CODECS,
    parse_time_to_seconds,
    format_timestamp,
    is_time_line,
    normalize_time_line,
    shift_time_str,
    shifted_time,
    shift_srt_content,
    parse_subtitles,
    rebuild_subtitles,
    build_vtt,
    apply_translated_blocks,
    reindex_srt,
    clean_subtitle_text,
    clean_extracted_srt,
    get_banner_block,
    translate_google,
    get_gemini_endpoint,
    translate_gemini,
    translate_custom_ai,
    translate_blocks,
    get_ffmpeg_path,
    get_ffprobe_path,
    get_remote_input_opts,
    select_embedded_subtitle_stream,
    extract_embedded_subtitle,
)

logger = logging.getLogger("subtitles_service")


def _update_chunk_progress(manager, cache_key, chunk_idx, text):
    if manager and cache_key and cache_key in manager.active_tasks:
        task_info = manager.active_tasks[cache_key]
        task_info["chunks"][chunk_idx] = text
        completed = len(task_info["chunks"])
        total_chunks = task_info.get("total_chunks", 8)
        task_info["progress"] = min(0.99, completed / total_chunks)


async def process_audio_chunk(
    video_url: str,
    start_sec: int,
    duration_sec: int,
    chunk_idx: int,
    api_key: str,
    sem: asyncio.Semaphore,
    cache_key: str = None,
    manager: "SubtitleGeneratorManager" = None
) -> str:
    result_srt = ""
    async with sem:
        chunk_file = os.path.join(CACHE_DIR, f"temp_chunk_{chunk_idx}_{start_sec}.mp3")
        hours = start_sec // 3600
        minutes = (start_sec % 3600) // 60
        seconds = start_sec % 60
        offset_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        ffmpeg_path = get_ffmpeg_path()

        # -accurate_seek keeps the chunk start exactly at start_sec; without it ffmpeg may
        # land on the previous keyframe and every transcribed cue of the chunk is shifted.
        cmd = [
            ffmpeg_path, "-y",
            *get_remote_input_opts(video_url),
            "-accurate_seek",
            "-ss", str(start_sec),
            "-t", str(duration_sec),
            "-i", video_url,
            "-vn",
            "-acodec", "libmp3lame",
            "-ar", "16000",
            "-ac", "1",
            "-ab", "32k",
            "-f", "mp3",
            chunk_file
        ]

        # Phase 1: Run ffmpeg with retries
        ffmpeg_success = False
        max_attempts = 3
        for attempt in range(max_attempts):
            logger.info(f"Extracting audio chunk {chunk_idx} (attempt {attempt+1}/{max_attempts}) starting at {offset_str}...")
            if os.path.exists(chunk_file):
                try:
                    os.remove(chunk_file)
                except Exception:
                    pass
            try:
                def run_sync():
                    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                result = await asyncio.to_thread(run_sync)

                # If exit code is 0, it means it completed successfully
                if result.returncode == 0:
                    ffmpeg_success = True
                    break
                else:
                    err_msg = result.stderr.decode('utf-8', errors='ignore') if result else "No result"
                    logger.warning(f"ffmpeg attempt {attempt+1} failed for chunk {chunk_idx}: {err_msg}")
            except Exception as e:
                logger.warning(f"ffmpeg attempt {attempt+1} raised exception for chunk {chunk_idx}: {e}")

            await asyncio.sleep(2.0 * (attempt + 1))

        if not ffmpeg_success:
            if os.path.exists(chunk_file):
                try:
                    os.remove(chunk_file)
                except Exception:
                    pass
            logger.error(f"Failed to extract audio chunk {chunk_idx} after {max_attempts} attempts.")
            _update_chunk_progress(manager, cache_key, chunk_idx, "")
            return None  # Return None to indicate a technical failure

        # Check size: if file size is tiny, it means we genuinely reached the end of the video
        if not os.path.exists(chunk_file) or os.path.getsize(chunk_file) < 5000:
            if os.path.exists(chunk_file):
                try:
                    os.remove(chunk_file)
                except Exception:
                    pass
            logger.info(f"Chunk {chunk_idx} is empty or reached end of video.")
            _update_chunk_progress(manager, cache_key, chunk_idx, "")
            return ""  # Return empty string to indicate genuine end of video (not a failure)

        # Phase 2: Transcribe via Gemini API with retries
        gemini_success = False
        for attempt in range(max_attempts):
            try:
                logger.info(f"Transcribing audio chunk {chunk_idx} via Gemini API (attempt {attempt+1}/{max_attempts})...")
                with open(chunk_file, "rb") as f:
                    audio_bytes = f.read()
                audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

                url = get_gemini_endpoint(api_key)

                prompt = (
                    "You are a professional transcriber. Transcribe the audio chunk into Vietnamese. "
                    "Generate standard SRT subtitle format. "
                    "Timestamps must start at 00:00:00,000 relative to the beginning of THIS audio chunk "
                    "and must match exactly when each line is spoken. "
                    "Output only the raw SRT subtitle content, with no markdown code blocks, no explanation, and no extra characters."
                )

                payload = {
                    "contents": [
                        {
                            "parts": [
                                {"text": prompt},
                                {
                                    "inlineData": {
                                        "mimeType": "audio/mp3",
                                        "data": audio_base64
                                    }
                                }
                            ]
                        }
                    ]
                }

                async with httpx.AsyncClient(timeout=90.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        srt_text = data["candidates"][0]["content"]["parts"][0]["text"]
                        if srt_text.startswith("```"):
                            srt_text = re.sub(r"^```[a-zA-Z0-9]*\n", "", srt_text)
                            srt_text = re.sub(r"\n```$", "", srt_text)
                        srt_text = srt_text.strip()
                        result_srt = shift_srt_content(srt_text, start_sec)
                        gemini_success = True
                        break
                    else:
                        logger.warning(f"Gemini attempt {attempt+1} failed for chunk {chunk_idx}: {resp.status_code} - {resp.text}")
            except Exception as e:
                logger.warning(f"Gemini attempt {attempt+1} raised exception for chunk {chunk_idx}: {e}")

            await asyncio.sleep(2.0 * (attempt + 1))

        # Clean up chunk file
        if os.path.exists(chunk_file):
            try:
                os.remove(chunk_file)
            except Exception:
                pass

        if not gemini_success:
            logger.error(f"Failed to transcribe audio chunk {chunk_idx} via Gemini API after {max_attempts} attempts.")
            _update_chunk_progress(manager, cache_key, chunk_idx, "")
            return None  # Return None to indicate a technical failure

        _update_chunk_progress(manager, cache_key, chunk_idx, result_srt)
        return result_srt


def get_progress_cues(percentage: int) -> str:
    timestamps = [
        ("00:00:30,000", "00:00:38,000"),
        ("00:01:30,000", "00:01:38,000"),
        ("00:03:00,000", "00:03:08,000"),
        ("00:05:00,000", "00:05:08,000"),
        ("00:10:00,000", "00:10:08,000"),
        ("00:15:00,000", "00:15:08,000"),
        ("00:20:00,000", "00:20:08,000"),
        ("00:25:00,000", "00:25:08,000"),
    ]
    lines = []
    start_idx = 9000
    for i, (start, end) in enumerate(timestamps):
        lines.append(f"{start_idx + i}")
        lines.append(f"{start} --> {end}")
        lines.append(f"<b>[Tiến trình dịch AI: {percentage}% - Vui lòng TẠM DỪNG video 1 phút để dịch hoàn tất]</b>")
        lines.append("")
    return "\n".join(lines)


async def get_stremio_local_stream_url(filename: str = None) -> str:
    """
    Queries Stremio's local streaming server (http://127.0.0.1:11470/stats.json) to detect the live video stream URL
    or local file path when playing from external torrent addons like TorrentsDB, Torrentio, etc.
    """
    ports = [11470, 11471, 11472]
    async with httpx.AsyncClient(timeout=2.0) as client:
        for p in ports:
            try:
                resp = await client.get(f"http://127.0.0.1:{p}/stats.json")
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict):
                        for infohash, details in data.items():
                            if isinstance(details, dict):
                                files = details.get("files", [])
                                cache_dir = details.get("opts", {}).get("path", "")
                                for idx, f in enumerate(files):
                                    f_name = f.get("name") or f.get("path") or ""

                                    # Match by filename if provided, otherwise select first video file
                                    if not filename or filename.lower() in f_name.lower() or f_name.lower() in filename.lower() or f_name.endswith(('.mkv', '.mp4', '.avi')):
                                        # 1. Prefer local disk path if file has started downloading
                                        if cache_dir:
                                            disk_path = os.path.join(cache_dir, f.get("path") or f_name)
                                            if os.path.exists(disk_path) and os.path.getsize(disk_path) > 1000:
                                                logger.info(f"Found active Stremio video file on local disk: {disk_path}")
                                                return disk_path

                                        # 2. Fallback to local HTTP stream URL on port 11470
                                        stream_url = f"http://127.0.0.1:{p}/{infohash}/{idx}"
                                        logger.info(f"Found active Stremio local HTTP stream URL: {stream_url}")
                                        return stream_url
            except Exception as e:
                logger.debug(f"Failed to query Stremio stats on port {p}: {e}")

    return None


class SubtitleGeneratorManager:
    def __init__(self):
        self.active_tasks = {}
        self.video_urls = {}

    def register_video_url(self, cache_key: str, video_url: str):
        if cache_key and video_url:
            self.video_urls[cache_key] = video_url

    async def get_or_start_translation(
        self,
        cache_key: str,
        source_url: str = None,
        video_url: str = None,
        filename: str = None
    ) -> tuple:
        """
        Returns (subtitle_content, progress)
        """
        if video_url:
            self.register_video_url(cache_key, video_url)
        else:
            video_url = self.video_urls.get(cache_key)

        # If video_url is not known yet and source_url is not provided, query Stremio's local streaming server (port 11470)
        if not source_url and not video_url:
            stremio_url = await get_stremio_local_stream_url(filename)
            if stremio_url:
                video_url = stremio_url
                self.register_video_url(cache_key, video_url)
            else:
                for _ in range(15):
                    await asyncio.sleep(0.2)
                    video_url = self.video_urls.get(cache_key)
                    if not video_url:
                        stremio_url = await get_stremio_local_stream_url(filename)
                        if stremio_url:
                            video_url = stremio_url
                            self.register_video_url(cache_key, video_url)
                    if video_url:
                        break

        cache_path = os.path.join(CACHE_DIR, f"{cache_key}.srt")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.read(), 1.0

        # Trigger background task if not already running
        if cache_key not in self.active_tasks:
            translation_source = getattr(Config, "SUBTITLE_TRANSLATION_SOURCE", "sub").lower()

            if translation_source == "audio" and video_url and Config.GEMINI_API_KEY:
                asyncio.create_task(self._run_transcription(cache_key, video_url, Config.GEMINI_API_KEY))
            else:
                if source_url:
                    asyncio.create_task(self._run_translation(cache_key, source_url=source_url, video_url=video_url))
                elif video_url:
                    asyncio.create_task(self._start_video_translation_flow(cache_key, video_url))

        # If the task is running (either just started or already active), wait up to 15 seconds
        if cache_key in self.active_tasks and not os.path.exists(cache_path):
            max_wait = 15.0
            wait_interval = 0.5
            waited = 0.0
            while cache_key in self.active_tasks and waited < max_wait:
                if os.path.exists(cache_path):
                    break
                task_info = self.active_tasks[cache_key]
                if task_info["type"] == "translation" and len(task_info["orig_blocks"]) > 0 and len(task_info["translated_blocks"]) >= len(task_info["orig_blocks"]):
                    break
                if task_info["type"] == "transcription" and task_info["chunks"].get(0):
                    break
                await asyncio.sleep(wait_interval)
                waited += wait_interval

        # Check again if finished and written to cache
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.read(), 1.0

        if cache_key in self.active_tasks:
            task_info = self.active_tasks[cache_key]
            progress = task_info["progress"]

            if task_info["type"] == "translation":
                orig_blocks = task_info["orig_blocks"]
                translated_blocks = task_info["translated_blocks"]

                merged_blocks = list(translated_blocks)
                translated_count = len(translated_blocks)

                if translated_count < len(orig_blocks):
                    merged_blocks.extend(orig_blocks[translated_count:])

                banner = get_banner_block(int(progress * 100))
                merged_blocks.insert(0, banner)

                lines = []
                for idx, b in enumerate(merged_blocks):
                    lines.append(f"{idx + 1}")
                    lines.append(shifted_time(b['time']))
                    lines.append(f"{b['text']}")
                    lines.append("")

                content = "\n".join(lines)
                if progress < 1.0:
                    content += "\n" + get_progress_cues(int(progress * 100))
                return content, progress
            else:
                chunks_data = task_info["chunks"]
                transcribed_parts = []
                for idx in sorted(chunks_data.keys()):
                    if chunks_data[idx]:
                        transcribed_parts.append(chunks_data[idx])

                merged_srt = "\n\n".join(transcribed_parts)
                banner_str = f"1\n00:00:00,000 --> 00:00:08,000\n<b>[Phụ đề AI đang được tạo - Tiến trình: {int(progress * 100)}%]</b>"
                content = reindex_srt(banner_str + "\n\n" + merged_srt)
                if progress < 1.0:
                    content += "\n\n" + get_progress_cues(int(progress * 100))
                return content, progress

        # Detailed diagnostic message when no translation or transcription task could run
        missing_reasons = []
        if not source_url:
            missing_reasons.append("Không tìm thấy tệp phụ đề rời (Eng/Sub)")
        if not Config.GEMINI_API_KEY:
            missing_reasons.append("Thiếu GEMINI_API_KEY để tạo phụ đề từ âm thanh (audio)")

        detail_text = " và ".join(missing_reasons) if missing_reasons else "Không thể tải phụ đề và tạo phụ đề AI thất bại"
        banner_str = f"1\n00:00:00,000 --> 00:00:08,000\n<b>[{detail_text}]</b>\n"
        return banner_str, 0.0

    async def _start_video_translation_flow(self, cache_key: str, video_url: str):
        self.active_tasks[cache_key] = {
            "type": "translation",
            "progress": 0.0,
            "orig_blocks": [],
            "translated_blocks": []
        }
        try:
            logger.info(f"Checking for embedded subtitles in video stream for {cache_key}...")
            embedded_srt = await extract_embedded_subtitle(video_url)
            if embedded_srt:
                logger.info(f"Embedded subtitle track extracted successfully! Translating for {cache_key}...")
                # allow_video_fallback=False: the content already comes from this video,
                # retrying the same video flow on failure would recurse forever.
                await self._run_translation(
                    cache_key,
                    content=embedded_srt,
                    video_url=video_url,
                    allow_video_fallback=False
                )
            else:
                translation_source = getattr(Config, "SUBTITLE_TRANSLATION_SOURCE", "sub").lower()
                if translation_source == "audio" and Config.GEMINI_API_KEY:
                    logger.info(f"No embedded subtitle track found. Falling back to Gemini audio transcription for {cache_key}...")
                    await self._run_transcription(cache_key, video_url, Config.GEMINI_API_KEY)
                else:
                    logger.warning(f"No embedded subtitle found and audio transcription fallback is disabled (SUBTITLE_TRANSLATION_SOURCE={translation_source}) for {cache_key}.")
        except Exception as e:
            logger.error(f"Error in video translation flow for {cache_key}: {e}")
        finally:
            if cache_key in self.active_tasks and not self.active_tasks[cache_key].get("orig_blocks") and not self.active_tasks[cache_key].get("chunks"):
                del self.active_tasks[cache_key]

    async def _run_translation(
        self,
        cache_key: str,
        source_url: str = None,
        content: str = None,
        video_url: str = None,
        allow_video_fallback: bool = True
    ):
        logger.info(f"Starting background subtitle translation for {cache_key}...")
        self.active_tasks[cache_key] = {
            "type": "translation",
            "progress": 0.0,
            "orig_blocks": [],
            "translated_blocks": []
        }

        try:
            if not content:
                if not source_url:
                    raise Exception("Neither source_url nor content provided for translation")
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                    resp = await client.get(source_url)
                    if resp.status_code != 200:
                        raise Exception(f"Failed to fetch original subtitle: {resp.status_code}")
                    content = resp.text

            header, blocks = parse_subtitles(content)
            if not blocks:
                raise Exception("Original subtitle returned 0 blocks")

            self.active_tasks[cache_key]["orig_blocks"] = blocks

            batch_size = 40
            chunks = [blocks[i:i+batch_size] for i in range(0, len(blocks), batch_size)]
            total_blocks_count = len(blocks)

            # Limit parallel API requests to 5 to prevent rate limits
            sem = asyncio.Semaphore(5)
            completed_chunks = set()
            translated_chunks_dict = {idx: chunk for idx, chunk in enumerate(chunks)}

            async def translate_chunk_with_sem(chunk_idx, chunk_data):
                async with sem:
                    try:
                        translated_chunk = await translate_blocks(chunk_data, Config.GEMINI_API_KEY)
                        translated_chunks_dict[chunk_idx] = translated_chunk
                        completed_chunks.add(chunk_idx)
                    except Exception as e:
                        logger.error(f"Failed to translate chunk {chunk_idx}: {e}")
                        completed_chunks.add(chunk_idx)

                    # Assemble all chunks to maintain exact chronological order
                    current_translated = []
                    for idx in sorted(translated_chunks_dict.keys()):
                        current_translated.extend(translated_chunks_dict[idx])

                    if cache_key in self.active_tasks:
                        self.active_tasks[cache_key]["translated_blocks"] = current_translated
                        translated_blocks_count = sum(len(translated_chunks_dict[idx]) for idx in completed_chunks)
                        progress = min(1.0, translated_blocks_count / total_blocks_count)
                        self.active_tasks[cache_key]["progress"] = progress

            tasks = [asyncio.create_task(translate_chunk_with_sem(idx, chunk)) for idx, chunk in enumerate(chunks)]
            await asyncio.gather(*tasks)

            if cache_key in self.active_tasks:
                final_blocks = list(self.active_tasks[cache_key]["translated_blocks"])
                credit_banner = {
                    "prefix": "1",
                    "time": "00:00:00,000 --> 00:00:08,000",
                    "text": "<b>[Phụ đề được dịch tự động sang Tiếng Việt bằng AI]</b>"
                }
                final_blocks.insert(0, credit_banner)

                lines = []
                for idx, b in enumerate(final_blocks):
                    lines.append(f"{idx + 1}")
                    lines.append(shifted_time(b['time']))
                    lines.append(f"{b['text']}")
                    lines.append("")

                final_content = "\n".join(lines)
                cache_path = os.path.join(CACHE_DIR, f"{cache_key}.srt")
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(final_content)

                logger.info(f"Finished background subtitle translation for {cache_key}.")

                # Trigger background TTS generation
                try:
                    from tts_service import tts_manager
                    asyncio.create_task(tts_manager.start_tts_generation(cache_key, final_content))
                except Exception as tts_e:
                    logger.error(f"Failed to start background TTS generation: {tts_e}")
        except Exception as e:
            logger.error(f"Error in background translation for {cache_key}: {e}")
            if video_url and allow_video_fallback:
                logger.info(f"Subtitle translation failed, attempting video fallback (embedded sub / audio transcription) for {cache_key}...")
                try:
                    await self._start_video_translation_flow(cache_key, video_url)
                except Exception as fb_e:
                    logger.error(f"Video translation fallback failed: {fb_e}")
        finally:
            if cache_key in self.active_tasks:
                del self.active_tasks[cache_key]

    async def _run_transcription(self, cache_key: str, video_url: str, gemini_key: str):
        logger.info(f"Starting background audio transcription for {cache_key}...")

        # Define variable chunk schedules: Chunk 0 is 5 minutes (300s) for instant startup,
        # subsequent chunks are 20 minutes (1200s) to cover the rest of the video.
        chunk_schedule = [(0, 0, 300)]
        current_start = 300
        chunk_duration = 1200
        for idx in range(1, 13):
            chunk_schedule.append((idx, current_start, chunk_duration))
            current_start += chunk_duration

        self.active_tasks[cache_key] = {
            "type": "transcription",
            "progress": 0.0,
            "chunks": {},
            "total_chunks": len(chunk_schedule)
        }

        try:
            sem = asyncio.Semaphore(1)

            tasks = []
            for chunk_idx, start_sec, duration_sec in chunk_schedule:
                t = asyncio.create_task(process_audio_chunk(video_url, start_sec, duration_sec, chunk_idx, gemini_key, sem, cache_key, self))
                tasks.append(t)

            results = await asyncio.gather(*tasks)

            if cache_key not in self.active_tasks:
                return

            # If any chunk failed (returned None), abort writing cache to prevent partial/broken subs from caching permanently
            if any(res is None for res in results):
                logger.error(f"One or more audio chunks failed to transcribe for {cache_key}. Aborting cache write so it can be retried.")
                return

            valid_results = {}
            for idx, res in enumerate(results):
                if res and res.strip():
                    valid_results[idx] = res

            self.active_tasks[cache_key]["chunks"] = valid_results
            self.active_tasks[cache_key]["progress"] = 1.0

            if valid_results:
                merged_srt = "\n\n".join(valid_results[i] for i in sorted(valid_results.keys()))
                banner_str = "1\n00:00:00,000 --> 00:00:08,000\n<b>[Phụ đề được dịch và tạo tự động bằng AI]</b>"
                final_content = reindex_srt(banner_str + "\n\n" + merged_srt)

                cache_path = os.path.join(CACHE_DIR, f"{cache_key}.srt")
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(final_content)
                logger.info(f"Finished background audio transcription for {cache_key}.")

                # Trigger background TTS generation
                try:
                    from tts_service import tts_manager
                    asyncio.create_task(tts_manager.start_tts_generation(cache_key, final_content))
                except Exception as tts_e:
                    logger.error(f"Failed to start background TTS generation: {tts_e}")
            else:
                logger.warning(f"Transcription yielded no valid subtitle content for {cache_key}.")
        except Exception as e:
            logger.error(f"Error in background transcription for {cache_key}: {e}")
        finally:
            if cache_key in self.active_tasks:
                del self.active_tasks[cache_key]


# Export singleton instance
subtitle_generator = SubtitleGeneratorManager()


async def translate_srt_fast_batch(srt_content: str, target_lang: str = "vi", return_status: bool = False):
    """
    Translates an SRT/VTT file to Vietnamese concurrently maintaining exact timestamps.
    Engines are tried in order (Gemini -> Lingva -> Custom AI) and the FIRST successful one wins.
    Output is always a valid WebVTT document (dot milliseconds).
    When return_status=True returns (vtt_content, translated_ok).
    """
    header, blocks = parse_subtitles(srt_content)

    if not blocks:
        return (srt_content, False) if return_status else srt_content

    original_texts = [b["text"] for b in blocks]

    def restore_original():
        for b, original in zip(blocks, original_texts):
            b["text"] = original

    def translated_ratio() -> float:
        changed = sum(1 for b, original in zip(blocks, original_texts) if b["text"].strip() != original.strip())
        return changed / max(1, len(blocks))

    def finish(ok: bool):
        # build_vtt writes real WebVTT timestamps; emitting SRT commas under a WEBVTT
        # header made players drop or mis-time every cue.
        content = build_vtt(blocks, SUBTITLE_TIME_OFFSET)
        return (content, ok) if return_status else content

    # 1. OPTION A: Translate via Gemini AI (Cinema-Grade, Natural Context, Fast)
    gemini_key = Config.GEMINI_API_KEY
    if gemini_key:
        try:
            logger.info(f"Translating {len(blocks)} subtitle blocks via Gemini API ({Config.GEMINI_MODEL})...")
            chunk_size = 150
            chunks = [blocks[i:i+chunk_size] for i in range(0, len(blocks), chunk_size)]

            async def translate_gemini_chunk(chunk_blocks):
                raw_chunk_srt = "\n\n".join(f"{idx+1}\n{b['time']}\n{b['text']}" for idx, b in enumerate(chunk_blocks))
                res = await translate_gemini(raw_chunk_srt, gemini_key, target_lang)
                if res.startswith("```"):
                    res = re.sub(r"^```[a-zA-Z0-9]*\n", "", res)
                    res = re.sub(r"\n```$", "", res)
                _, parsed = parse_subtitles(res.strip())
                # Cues are matched by timecode/id, never by position: one merged or dropped
                # line used to shift every following translation onto the wrong timestamp.
                applied = apply_translated_blocks(chunk_blocks, parsed)
                if applied == 0:
                    raise Exception("Gemini translation could not be aligned with the original cues")
                if applied < len(chunk_blocks):
                    logger.warning(f"Gemini aligned {applied}/{len(chunk_blocks)} cues; the rest keep their original text.")

            sem = asyncio.Semaphore(2)

            async def limited_gemini(c):
                async with sem:
                    await translate_gemini_chunk(c)

            await asyncio.gather(*[limited_gemini(c) for c in chunks])

            if translated_ratio() >= 0.5:
                logger.info("Gemini translation completed successfully.")
                return finish(True)
            logger.warning("Gemini translated too few blocks. Falling back to High-Speed Lingva Engine...")
            restore_original()
        except Exception as e:
            logger.warning(f"Gemini translation failed: {e}. Falling back to High-Speed Lingva Engine...")
            restore_original()

    # 2. OPTION B: Lingva High-Speed Multi-Instance Translator (No Bot Block, No Quota Limits)
    lingva_instances = [
        "https://lingva.ml",
        "https://lingva.garudalinux.org",
        "https://translate.plausibility.cloud"
    ]
    try:
        logger.info(f"Translating {len(blocks)} subtitle blocks via High-Speed Lingva Engine...")
        batch_size = 40
        chunks = [blocks[i:i+batch_size] for i in range(0, len(blocks), batch_size)]

        async def translate_lingva_chunk(chunk_blocks, client):
            tagged_lines = []
            for idx, b in enumerate(chunk_blocks):
                clean_text = b["text"].replace("\n", " ")
                tagged_lines.append(f"[[{idx}]] {clean_text}")
            joined_text = "\n".join(tagged_lines)

            for inst in lingva_instances:
                try:
                    url = f"{inst}/api/v1/auto/{target_lang}/{urllib.parse.quote(joined_text)}"
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        translated_joined = resp.json().get("translation", "")
                        extracted = {}
                        for m in re.finditer(r'\[\s*\[\s*(\d+)\s*\]\s*\]\s*([^\[]+)', translated_joined):
                            i = int(m.group(1))
                            t = m.group(2).strip()
                            extracted[i] = t
                        # Only explicitly tagged indexes are written back, so a dropped line
                        # never shifts the following cues onto the wrong timestamps.
                        for idx, b in enumerate(chunk_blocks):
                            if idx in extracted and extracted[idx]:
                                b["text"] = extracted[idx]
                        return
                except Exception:
                    continue

        async with httpx.AsyncClient(timeout=10.0) as client:
            await asyncio.gather(*[translate_lingva_chunk(c, client) for c in chunks], return_exceptions=True)

        if translated_ratio() >= 0.5:
            logger.info("Lingva translation completed successfully.")
            return finish(True)
        logger.warning("Lingva translated too few blocks. Falling back to Custom AI...")
        restore_original()
    except Exception as e:
        logger.warning(f"Lingva translation failed: {e}. Falling back to Custom AI...")
        restore_original()

    # 3. OPTION C: Custom AI
    custom_ai_url = Config.CUSTOM_AI_API_URL
    if custom_ai_url:
        try:
            logger.info(f"Translating {len(blocks)} subtitle blocks via Custom AI ({Config.CUSTOM_AI_MODEL})...")
            chunk_size = 100
            chunks = [blocks[i:i+chunk_size] for i in range(0, len(blocks), chunk_size)]

            async def translate_custom_chunk(chunk_blocks):
                raw_chunk_srt = "\n\n".join(f"{idx+1}\n{b['time']}\n{b['text']}" for idx, b in enumerate(chunk_blocks))
                res = await translate_custom_ai(raw_chunk_srt, target_lang)
                if res.startswith("```"):
                    res = re.sub(r"^```[a-zA-Z0-9]*\n", "", res)
                    res = re.sub(r"\n```$", "", res)
                _, parsed = parse_subtitles(res.strip())
                applied = apply_translated_blocks(chunk_blocks, parsed)
                if applied == 0:
                    raise Exception("Custom AI translation could not be aligned with the original cues")
                if applied < len(chunk_blocks):
                    logger.warning(f"Custom AI aligned {applied}/{len(chunk_blocks)} cues; the rest keep their original text.")

            await asyncio.gather(*[translate_custom_chunk(c) for c in chunks])
            if translated_ratio() >= 0.5:
                logger.info("Custom AI translation completed successfully.")
                return finish(True)
            logger.warning("Custom AI translated too few blocks.")
        except Exception as e:
            logger.warning(f"Custom AI translation failed: {e}")

    logger.error("All translation engines failed; returning the original (untranslated) subtitle.")
    return finish(translated_ratio() >= 0.5)


# In-memory mapping of item_id -> active stream video_url
STREAM_VIDEO_URL_CACHE = {}


async def get_or_generate_synced_vtt(media_type: str, item_id: str, video_url: Optional[str] = None) -> Optional[str]:
    """Retrieves or instantly generates an exact synced Vietnamese VTT subtitle track from embedded subtitle or OpenSubtitles."""
    clean_id = item_id.replace(":", "_").replace("/", "_")
    cache_file = os.path.join(CACHE_DIR, f"vi_sync_{clean_id}.vtt")

    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 100:
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass

    base_srt = None
    base_source = None
    target_video_url = (
        video_url
        or STREAM_VIDEO_URL_CACHE.get(item_id)
        or STREAM_VIDEO_URL_CACHE.get(clean_id)
        or STREAM_VIDEO_URL_CACHE.get(item_id.replace("_", ":"))
    )

    # 1. Primary Method: extract the subtitle embedded in the video itself.
    # It is always perfectly in sync with this exact release, unlike OpenSubtitles files.
    if target_video_url:
        try:
            logger.info(f"Extracting embedded subtitle directly from video: {str(target_video_url)[:80]}...")
            embedded_srt = await extract_embedded_subtitle(target_video_url)
            if embedded_srt and len(embedded_srt) > 100:
                logger.info(f"Successfully extracted embedded subtitle ({len(embedded_srt)} bytes) from video.")
                base_srt = embedded_srt
                base_source = "embedded"
            else:
                logger.info("No usable embedded subtitle track found, falling back to OpenSubtitles.")
        except Exception as e:
            logger.warning(f"Failed to extract embedded subtitle from video: {e}")
    else:
        logger.info(f"No video URL known for {item_id}; skipping embedded subtitle extraction.")

    # 2. Fallback Method: fetch a base English subtitle from OpenSubtitles (0.2s response time)
    if not base_srt:
        imdb_id = item_id
        if "_" in imdb_id and ":" not in imdb_id and not imdb_id.startswith("moviesdrive:"):
            parts = imdb_id.split("_")
            if len(parts) >= 3 and parts[0].startswith("tt"):
                imdb_id = f"{parts[0]}:{parts[1]}:{parts[2]}"
            elif len(parts) == 2 and parts[0].startswith("tt"):
                imdb_id = f"{parts[0]}:{parts[1]}"

        if imdb_id.startswith("moviesdrive:"):
            from moviesdrive_router import find_imdb_for_moviesdrive_id
            resolved = await find_imdb_for_moviesdrive_id(media_type, item_id)
            if resolved:
                imdb_id = resolved

        eng_subs = []
        if imdb_id and (imdb_id.startswith("tt") or ":" in imdb_id):
            url = (
                OPENSUBTITLES_BASE
                + urllib.parse.quote(str(media_type))
                + "/"
                + urllib.parse.quote(imdb_id)
                + ".json"
            )
            try:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        subs = resp.json().get("subtitles", [])
                        for s in subs:
                            if s.get("lang") in ("eng", "en"):
                                eng_subs.append(s.get("url"))
                        if not eng_subs and subs:
                            eng_subs.append(subs[0].get("url"))
            except Exception as e:
                logger.warning(f"Failed to fetch base subtitle for sync translation: {e}")

        for sub_url in eng_subs[:2]:
            try:
                async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                    resp = await client.get(sub_url)
                    if resp.status_code == 200 and len(resp.text) > 200:
                        base_srt = resp.text
                        base_source = "opensubtitles"
                        break
            except Exception:
                continue

    if not base_srt:
        return None

    logger.info(f"Translating base subtitle (source={base_source}) to Vietnamese...")

    # 3. Fast Batch Translate to Vietnamese
    vtt_content, translated_ok = await translate_srt_fast_batch(base_srt, target_lang="vi", return_status=True)
    if not vtt_content:
        return None

    # Never cache an untranslated subtitle, otherwise the English track sticks around forever.
    if translated_ok:
        try:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(vtt_content)
        except Exception as e:
            logger.warning(f"Failed to write cache for {cache_file}: {e}")
    else:
        logger.warning(f"Translation failed for {item_id}; serving the untranslated track without caching it.")

    return vtt_content
