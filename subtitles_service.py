import os
import re
import json
import httpx
import base64
import urllib.parse
import asyncio
import logging
import shutil
import subprocess
import tempfile
from config import Config

logger = logging.getLogger("subtitles_service")

# Ensure subtitles cache directory exists (in system temp to prevent Uvicorn reload loops)
CACHE_DIR = os.path.join(tempfile.gettempdir(), "stremio_telegram_subtitles")
os.makedirs(CACHE_DIR, exist_ok=True)

def parse_subtitles(content: str) -> tuple:
    """
    Parses SRT or VTT subtitle content.
    Returns (header, blocks) where blocks is a list of dicts:
    {"prefix": str, "time": str, "text": str}
    """
    content = content.replace('\r\n', '\n')
    header = ""
    if content.strip().startswith("WEBVTT"):
        parts = re.split(r'\n\s*\n', content, maxsplit=1)
        if len(parts) > 1 and "-->" not in parts[0]:
            header = parts[0] + "\n\n"
            content = parts[1]
            
    blocks = []
    raw_blocks = re.split(r'\n\s*\n', content.strip())
    for raw_block in raw_blocks:
        lines = [l.strip() for l in raw_block.split('\n') if l.strip()]
        time_idx = -1
        for idx, line in enumerate(lines):
            if "-->" in line:
                time_idx = idx
                break
        if time_idx != -1:
            index_lines = lines[:time_idx]
            time_line = lines[time_idx]
            text_lines = lines[time_idx+1:]
            
            blocks.append({
                "prefix": "\n".join(index_lines) if index_lines else "",
                "time": time_line,
                "text": "\n".join(text_lines)
            })
    return header, blocks

def rebuild_subtitles(header: str, blocks: list) -> str:
    lines = []
    if header:
        lines.append(header.strip())
        lines.append("")
    for b in blocks:
        if b["prefix"]:
            lines.append(f"{b['prefix']}")
        lines.append(f"{b['time']}")
        lines.append(f"{b['text']}")
        lines.append("")
    return "\n".join(lines)

def reindex_srt(srt_content: str) -> str:
    _, blocks = parse_subtitles(srt_content)
    lines = []
    for idx, b in enumerate(blocks):
        lines.append(f"{idx + 1}")
        lines.append(f"{b['time']}")
        lines.append(f"{b['text']}")
        lines.append("")
    return "\n".join(lines)

def get_banner_block(progress: int) -> dict:
    return {
        "prefix": "1",
        "time": "00:00:00,000 --> 00:00:08,000",
        "text": f"<b>[Phụ đề dịch tự động bằng AI - Tiến trình: {progress}%]</b>"
    }

async def translate_google(text: str, target_lang: str = "vi") -> str:
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&dt=t&sl=auto&tl={target_lang}&q={urllib.parse.quote(text)}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            translated = "".join([item[0] for item in data[0] if item[0]])
            return translated
        else:
            raise Exception(f"Google Translate API status {resp.status_code}")

async def translate_gemini(text: str, api_key: str, target_lang: str = "vi") -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
    prompt = (
        f"Translate the following subtitles into natural, conversational Vietnamese. "
        f"Keep all timestamps, line numbers, and formatting exactly as they are. "
        f"Output only the translated SRT subtitles and nothing else:\n\n{text}"
    )
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.2
        }
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            try:
                translated = data["candidates"][0]["content"]["parts"][0]["text"]
                return translated
            except (KeyError, IndexError):
                raise Exception("Invalid Gemini API response structure")
        else:
            raise Exception(f"Gemini API status {resp.status_code}: {resp.text}")

async def translate_blocks(blocks: list, api_key: str = None, target_lang: str = "vi") -> list:
    translated_blocks = []
    batch_size = 100
    
    for i in range(0, len(blocks), batch_size):
        chunk = blocks[i:i+batch_size]
        success = False
        
        if api_key:
            try:
                chunk_srt = ""
                for idx, b in enumerate(chunk):
                    prefix = b["prefix"] if b["prefix"] else str(idx + 1)
                    chunk_srt += f"{prefix}\n{b['time']}\n{b['text']}\n\n"
                
                translated_srt = await translate_gemini(chunk_srt, api_key, target_lang)
                _, parsed_chunk = parse_subtitles(translated_srt)
                
                if len(parsed_chunk) == len(chunk):
                    for b_orig, b_trans in zip(chunk, parsed_chunk):
                        translated_blocks.append({
                            "prefix": b_orig["prefix"],
                            "time": b_orig["time"],
                            "text": b_trans["text"].strip()
                        })
                    success = True
                    logger.info(f"Batch {i//batch_size + 1} translated successfully via Gemini.")
                else:
                    logger.warning(f"Gemini translation returned mismatch block count: expected {len(chunk)}, got {len(parsed_chunk)}. Falling back to Google Translate.")
            except Exception as e:
                logger.error(f"Gemini translation failed for batch {i//batch_size + 1}: {e}. Falling back to Google Translate.")
        
        if not success:
            sub_batch_size = 30
            for j in range(0, len(chunk), sub_batch_size):
                sub_chunk = chunk[j:j+sub_batch_size]
                chunk_texts = [b["text"].replace("\n", " <br> ") for b in sub_chunk]
                batch_text = "\n".join(chunk_texts)
                
                try:
                    translated_raw = await translate_google(batch_text, target_lang)
                    translated_lines = translated_raw.replace('\r\n', '\n').split('\n')
                    if len(translated_lines) > len(sub_chunk) and not translated_lines[-1].strip():
                        translated_lines.pop()
                        
                    if len(translated_lines) == len(sub_chunk):
                        for block, trans_line in zip(sub_chunk, translated_lines):
                            trans_text = re.sub(r'\s*<\s*br\s*/?\s*>\s*', '\n', trans_line, flags=re.IGNORECASE)
                            translated_blocks.append({
                                "prefix": block["prefix"],
                                "time": block["time"],
                                "text": trans_text.strip()
                            })
                    else:
                        raise ValueError(f"Size mismatch: expected {len(sub_chunk)}, got {len(translated_lines)}")
                except Exception as ex:
                    logger.warning(f"Google Translate batch failed for sub-batch {j//sub_batch_size}: {ex}. Falling back to block-by-block.")
                    for block in sub_chunk:
                        try:
                            trans_val = await translate_google(block["text"].replace("\n", " <br> "), target_lang)
                            trans_text = re.sub(r'\s*<\s*br\s*/?\s*>\s*', '\n', trans_val, flags=re.IGNORECASE)
                            translated_blocks.append({
                                "prefix": block["prefix"],
                                "time": block["time"],
                                "text": trans_text.strip()
                            })
                        except Exception as block_ex:
                            logger.error(f"Failed to translate block: {block_ex}")
                            translated_blocks.append(block)
                            
    return translated_blocks

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
        
        logger.info(f"Extracting audio chunk {chunk_idx} starting at {offset_str}...")
        
        ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
        
        cmd = [
            ffmpeg_path, "-y",
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
        
        logger.info(f"Running ffmpeg command: {' '.join(cmd)}")
        
        try:
            def run_sync():
                return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
            result = await asyncio.to_thread(run_sync)
            if result.returncode != 0:
                logger.error(f"ffmpeg failed for chunk {chunk_idx}: {result.stderr.decode('utf-8', errors='ignore')}")
                _update_chunk_progress(manager, cache_key, chunk_idx, "")
                return ""
        except Exception as e:
            logger.exception(f"Failed to run ffmpeg for chunk {chunk_idx}")
            _update_chunk_progress(manager, cache_key, chunk_idx, "")
            return ""
            
        if not os.path.exists(chunk_file) or os.path.getsize(chunk_file) < 5000:
            if os.path.exists(chunk_file):
                os.remove(chunk_file)
            logger.info(f"Chunk {chunk_idx} is empty or reached end of video.")
            _update_chunk_progress(manager, cache_key, chunk_idx, "")
            return ""
            
        try:
            logger.info(f"Transcribing audio chunk {chunk_idx} via Gemini API...")
            with open(chunk_file, "rb") as f:
                audio_bytes = f.read()
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
            
            prompt = (
                f"You are a professional transcriber. Transcribe the audio chunk into Vietnamese. "
                f"Generate standard SRT subtitle format. "
                f"Make sure all timestamps in the SRT are offset by adding {offset_str} (HH:MM:SS) to them. "
                f"For example, if a conversation happens at 00:01:15 in this chunk, the timestamp in the SRT must be offset "
                f"by {offset_str} and displayed as {hours:02d}:{minutes + 1:02d}:{seconds + 15:02d},000. "
                f"Output only the raw SRT subtitle content, with no markdown code blocks, no explanation, and no extra characters."
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
                    srt_text = srt_text.replace("```srt", "").replace("```", "").strip()
                    result_srt = srt_text
                else:
                    logger.error(f"Gemini transcription failed for chunk {chunk_idx}: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"Error during Gemini transcription of chunk {chunk_idx}: {e}")
        finally:
            if os.path.exists(chunk_file):
                os.remove(chunk_file)
                
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

class SubtitleGeneratorManager:
    def __init__(self):
        self.active_tasks = {}

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
        cache_path = os.path.join(CACHE_DIR, f"{cache_key}.srt")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.read(), 1.0
                
        # Trigger background task if not already running
        if cache_key not in self.active_tasks:
            if source_url:
                asyncio.create_task(self._run_translation(cache_key, source_url))
            elif video_url and Config.GEMINI_API_KEY:
                if shutil.which("ffmpeg") is not None:
                    asyncio.create_task(self._run_transcription(cache_key, video_url, Config.GEMINI_API_KEY))
                else:
                    logger.warning("ffmpeg is not installed, audio transcription is disabled.")
                    
        # If the task is running (either just started or already active), wait up to 12 seconds
        if cache_key in self.active_tasks and not os.path.exists(cache_path):
            max_wait = 12.0
            wait_interval = 0.5
            waited = 0.0
            while cache_key in self.active_tasks and waited < max_wait:
                if os.path.exists(cache_path):
                    break
                task_info = self.active_tasks[cache_key]
                if task_info["type"] == "translation" and len(task_info["translated_blocks"]) >= len(task_info["orig_blocks"]):
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
                    lines.append(f"{b['time']}")
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

        banner_str = "1\n00:00:00,000 --> 00:00:08,000\n<b>[Không tìm thấy phụ đề gốc và thiếu cấu hình AI]</b>\n"
        return banner_str, 0.0

    async def _run_translation(self, cache_key: str, source_url: str):
        logger.info(f"Starting background subtitle translation for {cache_key}...")
        self.active_tasks[cache_key] = {
            "type": "translation",
            "progress": 0.0,
            "orig_blocks": [],
            "translated_blocks": []
        }
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(source_url)
                if resp.status_code != 200:
                    raise Exception(f"Failed to fetch original subtitle: {resp.status_code}")
                content = resp.text
                
            header, blocks = parse_subtitles(content)
            self.active_tasks[cache_key]["orig_blocks"] = blocks
            
            batch_size = 100
            for i in range(0, len(blocks), batch_size):
                chunk = blocks[i:i+batch_size]
                translated_chunk = await translate_blocks(chunk, Config.GEMINI_API_KEY)
                
                if cache_key not in self.active_tasks:
                    break
                    
                self.active_tasks[cache_key]["translated_blocks"].extend(translated_chunk)
                progress = min(1.0, len(self.active_tasks[cache_key]["translated_blocks"]) / len(blocks))
                self.active_tasks[cache_key]["progress"] = progress
                
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
                    lines.append(f"{b['time']}")
                    lines.append(f"{b['text']}")
                    lines.append("")
                    
                final_content = "\n".join(lines)
                cache_path = os.path.join(CACHE_DIR, f"{cache_key}.srt")
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(final_content)
                    
                logger.info(f"Finished background subtitle translation for {cache_key}.")
        except Exception as e:
            logger.error(f"Error in background translation for {cache_key}: {e}")
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
            else:
                logger.warning(f"Transcription yielded no valid subtitle content for {cache_key}.")
        except Exception as e:
            logger.error(f"Error in background transcription for {cache_key}: {e}")
        finally:
            if cache_key in self.active_tasks:
                del self.active_tasks[cache_key]

# Export singleton instance
subtitle_generator = SubtitleGeneratorManager()
