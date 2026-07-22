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

def shift_time_str(time_str: str, offset_seconds: float) -> str:
    parts = time_str.split("-->")
    if len(parts) != 2:
        return time_str
    
    start_part = parts[0].strip()
    end_part = parts[1].strip()
    
    def parse_single_time(t_str: str) -> float:
        t_str_norm = t_str.replace(",", ".")
        time_parts = t_str_norm.split(":")
        try:
            if len(time_parts) == 3:
                h, m, s = time_parts
                return float(h) * 3600 + float(m) * 60 + float(s)
            elif len(time_parts) == 2:
                m, s = time_parts
                return float(m) * 60 + float(s)
            else:
                return float(t_str_norm)
        except ValueError:
            return 0.0

    def format_single_time(seconds: float, is_vtt: bool = False) -> str:
        if seconds < 0:
            seconds = 0.0
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        sec_int = int(s)
        ms = int(round((s - sec_int) * 1000))
        if ms >= 1000:
            ms = 0
            sec_int += 1
            if sec_int >= 60:
                sec_int = 0
                m += 1
                if m >= 60:
                    m = 0
                    h += 1
        sep = "." if is_vtt else ","
        return f"{h:02d}:{m:02d}:{sec_int:02d}{sep}{ms:03d}"

    is_vtt = "." in time_str
    new_start_sec = parse_single_time(start_part) + offset_seconds
    new_end_sec = parse_single_time(end_part) + offset_seconds
    
    return f"{format_single_time(new_start_sec, is_vtt)} --> {format_single_time(new_end_sec, is_vtt)}"

def shift_srt_content(srt_content: str, offset_seconds: float) -> str:
    if not srt_content.strip() or offset_seconds == 0:
        return srt_content
    header, blocks = parse_subtitles(srt_content)
    for b in blocks:
        b["time"] = shift_time_str(b["time"], offset_seconds)
    return rebuild_subtitles(header, blocks)

def parse_subtitles(content: str) -> tuple:
    """
    Parses SRT or VTT subtitle content.
    Returns (header, blocks) where blocks is a list of dicts:
    {"prefix": str, "time": str, "text": str}
    """
    content = content.replace('\r\n', '\n')
    
    # Normalize double-spaced subtitles (very common in translated/OpenSubtitles files)
    if "\n\n\n" in content:
        content = re.sub(r'\n{3,}', '__BLOCK_SEP__', content)
        content = content.replace('\n\n', '\n')
        content = content.replace('__BLOCK_SEP__', '\n\n')
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
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{Config.GEMINI_MODEL}:generateContent?key={api_key}"
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

async def translate_custom_ai(text: str, target_lang: str = "vi") -> str:
    url = Config.CUSTOM_AI_API_URL.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    api_key = Config.CUSTOM_AI_API_KEY
    model = Config.CUSTOM_AI_MODEL
    stream_mode = Config.CUSTOM_AI_STREAM
    
    prompt = (
        f"Translate the following subtitles into natural, conversational Vietnamese. "
        f"Keep all timestamps, line numbers, and formatting exactly as they are. "
        f"Output only the translated SRT subtitles and nothing else:\n\n{text}"
    )
    
    headers = {
        "Content-Type": "application/json"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": stream_mode
    }
    
    translated_text = ""
    async with httpx.AsyncClient(timeout=60.0) as client:
        if stream_mode:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    err_content = await response.aread()
                    raise Exception(f"Custom AI API status {response.status_code}: {err_content.decode('utf-8', errors='ignore')}")
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data_json = json.loads(data_str)
                            content = data_json["choices"][0]["delta"].get("content", "")
                            translated_text += content
                        except Exception:
                            pass
        else:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code != 200:
                raise Exception(f"Custom AI API status {response.status_code}: {response.text}")
            data_json = response.json()
            try:
                translated_text = data_json["choices"][0]["message"]["content"]
            except (KeyError, IndexError):
                raise Exception("Invalid Custom AI API response structure (non-streaming)")
                
    if translated_text.startswith("```"):
        translated_text = re.sub(r"^```[a-zA-Z0-9]*\n", "", translated_text)
        translated_text = re.sub(r"\n```$", "", translated_text)
    return translated_text.strip()

async def translate_blocks(blocks: list, api_key: str = None, target_lang: str = "vi") -> list:
    translated_blocks = []
    batch_size = 40
    
    for i in range(0, len(blocks), batch_size):
        chunk = blocks[i:i+batch_size]
        success = False
        
        # Build SRT formatting block for AI models
        chunk_srt = ""
        for idx, b in enumerate(chunk):
            prefix = b["prefix"] if b["prefix"] else str(idx + 1)
            chunk_srt += f"{prefix}\n{b['time']}\n{b['text']}\n\n"

        # 1. Try Custom AI API if configured
        if Config.CUSTOM_AI_API_URL:
            try:
                logger.info(f"Translating batch {i//batch_size + 1} using Custom AI API (Model: {Config.CUSTOM_AI_MODEL})...")
                translated_srt = await translate_custom_ai(chunk_srt, target_lang)
                _, parsed_chunk = parse_subtitles(translated_srt)
                
                if len(parsed_chunk) == len(chunk):
                    for b_orig, b_trans in zip(chunk, parsed_chunk):
                        translated_blocks.append({
                            "prefix": b_orig["prefix"],
                            "time": b_orig["time"],
                            "text": b_trans["text"].strip()
                        })
                    success = True
                    logger.info(f"Batch {i//batch_size + 1} translated successfully via Custom AI.")
                else:
                    logger.warning(f"Custom AI translation returned mismatch block count: expected {len(chunk)}, got {len(parsed_chunk)}.")
            except Exception as e:
                logger.error(f"Custom AI translation failed for batch {i//batch_size + 1}: {e}.")
        
        # 2. Try Gemini API if Custom AI is not configured or failed, and gemini api_key is available
        if not success and api_key:
            try:
                logger.info(f"Falling back to Gemini API (Model: {Config.GEMINI_MODEL}) for batch {i//batch_size + 1}...")
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

def get_ffmpeg_path() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    proj_bin = os.path.join(base_dir, "ffmpeg.exe")
    if os.path.exists(proj_bin):
        return proj_bin
    return shutil.which("ffmpeg") or "ffmpeg"

def get_ffprobe_path() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    proj_bin = os.path.join(base_dir, "ffprobe.exe")
    if os.path.exists(proj_bin):
        return proj_bin
    return shutil.which("ffprobe") or "ffprobe"

async def extract_embedded_subtitle(video_url: str) -> str:
    """
    Inspects video_url using ffprobe for embedded subtitle streams.
    Extracts the best matching text subtitle stream (English or first available) to SRT format.
    Returns SRT content string, or None if no text subtitle stream found/extracted.
    """
    ffprobe_bin = get_ffprobe_path()
    cmd_probe = [
        ffprobe_bin,
        "-v", "error",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "s",
        "-analyzeduration", "10000000",
        "-probesize", "10000000",
        video_url
    ]
    
    logger.info(f"Running ffprobe to detect embedded subtitles on {video_url}...")
    try:
        def run_probe():
            return subprocess.run(cmd_probe, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=25)
        
        probe_res = await asyncio.to_thread(run_probe)
        if probe_res.returncode != 0 or not probe_res.stdout:
            err_log = probe_res.stderr.strip() if probe_res.stderr else "No output"
            logger.warning(f"ffprobe returned code {probe_res.returncode}: {err_log}")
            return None
            
        data = json.loads(probe_res.stdout)
        streams = data.get("streams", [])
        logger.info(f"ffprobe detected {len(streams)} embedded subtitle stream(s).")
        if not streams:
            return None
            
        text_codecs = {"subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text", "sub", "hdmv_pgs_subtitle"}
        chosen_stream_index = None
        
        # 1. Prefer English text-based subtitle stream
        for s in streams:
            codec = s.get("codec_name", "").lower()
            tags = s.get("tags", {})
            lang = tags.get("language", "").lower()
            title = tags.get("title", "").lower()
            
            if (lang in ("eng", "en") or "english" in title or "eng" in title):
                chosen_stream_index = s.get("index")
                logger.info(f"Selected English embedded subtitle stream index {chosen_stream_index} ({codec}, lang={lang}, title={title}).")
                break
                
        # 2. Prefer any text-based subtitle stream
        if chosen_stream_index is None:
            for s in streams:
                codec = s.get("codec_name", "").lower()
                if codec in text_codecs:
                    chosen_stream_index = s.get("index")
                    logger.info(f"Selected text-based embedded subtitle stream index {chosen_stream_index} ({codec}).")
                    break
                    
        # 3. Fallback to first subtitle stream overall
        if chosen_stream_index is None and streams:
            chosen_stream_index = streams[0].get("index")
            logger.info(f"Fallback to first embedded subtitle stream index {chosen_stream_index}.")
            
        if chosen_stream_index is None:
            return None
            
        # Extract stream via ffmpeg
        ffmpeg_bin = get_ffmpeg_path()
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tmp:
            tmp_srt_path = tmp.name
            
        cmd_extract = [
            ffmpeg_bin, "-y",
            "-analyzeduration", "10000000",
            "-probesize", "10000000",
            "-i", video_url,
            "-map", f"0:{chosen_stream_index}",
            "-t", "3600",
            "-f", "srt",
            tmp_srt_path
        ]
        
        logger.info(f"Running ffmpeg extraction for stream 0:{chosen_stream_index}...")
        def run_extract():
            return subprocess.run(cmd_extract, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            
        extract_res = await asyncio.to_thread(run_extract)
        logger.info(f"ffmpeg extraction completed with status code {extract_res.returncode}.")
        
        srt_content = None
        if os.path.exists(tmp_srt_path):
            if os.path.getsize(tmp_srt_path) > 10:
                with open(tmp_srt_path, "r", encoding="utf-8", errors="ignore") as f:
                    srt_content = f.read()
            try:
                os.remove(tmp_srt_path)
            except Exception:
                pass
                
        if srt_content and srt_content.strip():
            logger.info(f"Successfully extracted embedded subtitle ({len(srt_content)} bytes, {len(srt_content.splitlines())} lines).")
            return srt_content.strip()
        else:
            err_output = extract_res.stderr.decode('utf-8', errors='ignore') if extract_res else ""
            logger.warning(f"ffmpeg extraction yielded 0 bytes. Stderr: {err_output}")
            
    except Exception as e:
        logger.warning(f"Failed to extract embedded subtitle: {e}")
        
    return None

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
                
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{Config.GEMINI_MODEL}:generateContent?key={api_key}"
                
                prompt = (
                    "You are a professional transcriber. Transcribe the audio chunk into Vietnamese. "
                    "Generate standard SRT subtitle format. "
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
                if get_ffmpeg_path() is not None:
                    asyncio.create_task(self._run_transcription(cache_key, video_url, Config.GEMINI_API_KEY))
                else:
                    logger.warning("ffmpeg is not installed, audio transcription is disabled. Falling back to translating subtitles.")
                    if source_url:
                        asyncio.create_task(self._run_translation(cache_key, source_url=source_url, video_url=video_url))
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
                await self._run_translation(cache_key, content=embedded_srt, video_url=video_url)
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

    async def _run_translation(self, cache_key: str, source_url: str = None, content: str = None, video_url: str = None):
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
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(source_url)
                    if resp.status_code != 200:
                        raise Exception(f"Failed to fetch original subtitle: {resp.status_code}")
                    content = resp.text
                
            header, blocks = parse_subtitles(content)
            if not blocks:
                raise Exception("Original subtitle returned 0 blocks")
                
            self.active_tasks[cache_key]["orig_blocks"] = blocks
            
            batch_size = 40
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
                
                # Trigger background TTS generation
                try:
                    from tts_service import tts_manager
                    asyncio.create_task(tts_manager.start_tts_generation(cache_key, final_content))
                except Exception as tts_e:
                    logger.error(f"Failed to start background TTS generation: {tts_e}")
        except Exception as e:
            logger.error(f"Error in background translation for {cache_key}: {e}")
            if video_url:
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
