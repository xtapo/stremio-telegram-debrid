"""
Shared subtitle helpers: parsing, timing, cleaning and the translation engines.

Split out of subtitles_service.py to keep both files readable. subtitles_service
re-exports every public helper, so existing imports keep working unchanged.
"""
import os
import re
import json
import httpx
import urllib.parse
import asyncio
import logging
import shutil
import subprocess
import tempfile
from typing import Optional
from config import Config

logger = logging.getLogger("subtitles_service")

# Ensure subtitles cache directory exists (in system temp to prevent Uvicorn reload loops)
CACHE_DIR = os.path.join(tempfile.gettempdir(), "stremio_telegram_subtitles")
os.makedirs(CACHE_DIR, exist_ok=True)

# API endpoints are built with plain string concatenation on purpose:
# f-strings previously wrapped these URLs in stray curly braces, which produced
# invalid URLs like "{https://...}" and made every request fail.
GOOGLE_TRANSLATE_ENDPOINT = "https://translate.googleapis.com/translate_a/single"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models/"
OPENSUBTITLES_BASE = "https://opensubtitles-v3.strem.io/subtitles/"

# Manual timing correction in seconds, applied to every generated track.
# Positive value = subtitles appear later. Set SUBTITLE_TIME_OFFSET in .env when a
# fallback (OpenSubtitles) track belongs to a different release than the video.
try:
    SUBTITLE_TIME_OFFSET = float(
        getattr(Config, "SUBTITLE_TIME_OFFSET", None)
        or os.getenv("SUBTITLE_TIME_OFFSET", "0")
        or 0
    )
except (TypeError, ValueError):
    SUBTITLE_TIME_OFFSET = 0.0

# Text based subtitle codecs: ffmpeg can convert these straight to SRT.
TEXT_SUB_CODECS = {
    "subrip", "srt", "ass", "ssa", "webvtt", "vtt", "mov_text", "text",
    "microdvd", "subviewer", "subviewer1", "jacosub", "sami", "realtext",
    "mpl2", "pjs", "vplayer", "stl", "eia_608", "hdmv_text_subtitle",
}

# Bitmap (image) based subtitle codecs: ffmpeg CANNOT turn these into text without OCR.
# Selecting one of them used to make the whole embedded-subtitle extraction fail silently.
IMAGE_SUB_CODECS = {
    "hdmv_pgs_subtitle", "pgssub", "dvd_subtitle", "dvdsub",
    "dvb_subtitle", "dvbsub", "dvb_teletext", "xsub",
}


def parse_time_to_seconds(t_str: str) -> float:
    """Parses 'hh:mm:ss,mmm', 'hh:mm:ss.mmm', 'mm:ss.mmm' or plain seconds."""
    t_str = (t_str or "").strip().replace(",", ".")
    if not t_str:
        return 0.0
    sign = -1.0 if t_str.startswith("-") else 1.0
    t_str = t_str.lstrip("+-")
    parts = t_str.split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
            return sign * (float(h) * 3600 + float(m) * 60 + float(s))
        if len(parts) == 2:
            m, s = parts
            return sign * (float(m) * 60 + float(s))
        return sign * float(t_str)
    except ValueError:
        return 0.0


def format_timestamp(seconds: float, as_vtt: bool = False) -> str:
    """Formats seconds as an SRT (comma) or WebVTT (dot) timestamp."""
    if seconds is None or seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    sep = "." if as_vtt else ","
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def is_time_line(line: str) -> bool:
    """True when the line is a cue timing line ('00:01:02,500 --> 00:01:05,000')."""
    return "-->" in line and bool(re.search(r"\d{1,3}\s*:\s*\d{1,2}", line))


def _split_time_line(time_line: str) -> tuple:
    """Returns (start_raw, end_raw, trailing_cue_settings)."""
    left, right = time_line.split("-->", 1)
    right = right.strip()
    match = re.match(r"^(\S+)\s*(.*)$", right)
    if match:
        return left.strip(), match.group(1), match.group(2).strip()
    return left.strip(), right, ""


def normalize_time_line(time_line: str, as_vtt: bool = False) -> str:
    """Rewrites a cue timing line into a canonical SRT or WebVTT form."""
    if not time_line or "-->" not in time_line:
        return (time_line or "").strip()
    start_raw, end_raw, settings = _split_time_line(time_line)
    line = (
        format_timestamp(parse_time_to_seconds(start_raw), as_vtt)
        + " --> "
        + format_timestamp(parse_time_to_seconds(end_raw), as_vtt)
    )
    if settings:
        line += " " + settings
    return line


def shift_time_str(time_str: str, offset_seconds: float) -> str:
    """Shifts a cue timing line by offset_seconds while keeping its SRT/VTT style."""
    if not time_str or "-->" not in time_str:
        return time_str
    start_raw, end_raw, settings = _split_time_line(time_str)
    as_vtt = "." in start_raw
    line = (
        format_timestamp(parse_time_to_seconds(start_raw) + offset_seconds, as_vtt)
        + " --> "
        + format_timestamp(parse_time_to_seconds(end_raw) + offset_seconds, as_vtt)
    )
    if settings:
        line += " " + settings
    return line


def shifted_time(time_line: str) -> str:
    """Applies the global SUBTITLE_TIME_OFFSET correction (no-op when it is 0)."""
    if not SUBTITLE_TIME_OFFSET:
        return time_line
    return shift_time_str(time_line, SUBTITLE_TIME_OFFSET)


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

    Splitting is driven by the TIMESTAMP lines, not by blank lines. Subtitle files in
    the wild are single spaced, double spaced, or contain stray blank lines inside a
    cue; the previous blank-line splitter collapsed such a file into one giant cue,
    which destroyed the timing of every single line.
    """
    if not content:
        return "", []

    content = content.replace("\r\n", "\n").replace("\r", "\n").replace("\ufeff", "")

    header = ""
    body = content
    if content.lstrip().startswith("WEBVTT"):
        stripped = content.lstrip()
        first_line, _, rest = stripped.partition("\n")
        header = first_line.strip() + "\n\n"
        body = rest

    lines = body.split("\n")
    time_indexes = [i for i, line in enumerate(lines) if is_time_line(line)]
    if not time_indexes:
        return header, []

    def has_id_line_above(t_idx: int) -> bool:
        prev_idx = t_idx - 1
        if prev_idx < 0:
            return False
        candidate = lines[prev_idx].strip()
        if not candidate:
            return False
        if re.fullmatch(r"\d+", candidate):
            return True
        above = lines[prev_idx - 1].strip() if prev_idx - 1 >= 0 else ""
        return not above and " " not in candidate and len(candidate) <= 40

    blocks = []
    for n, t_idx in enumerate(time_indexes):
        prefix = lines[t_idx - 1].strip() if has_id_line_above(t_idx) else ""

        if n + 1 < len(time_indexes):
            next_idx = time_indexes[n + 1]
            end = next_idx - 1 if has_id_line_above(next_idx) else next_idx
        else:
            end = len(lines)

        text_lines = [l.strip() for l in lines[t_idx + 1:end]]
        text = "\n".join([l for l in text_lines if l])

        blocks.append({
            "prefix": prefix,
            "time": normalize_time_line(lines[t_idx]),
            "text": text,
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


def build_vtt(blocks: list, offset_seconds: float = 0.0) -> str:
    """
    Serializes cues as a VALID WebVTT file.
    WebVTT requires a dot as the millisecond separator; the previous code emitted a
    'WEBVTT' header on top of SRT comma timestamps, so players silently dropped or
    mis-timed the cues.
    """
    lines = ["WEBVTT", ""]
    counter = 0
    for b in blocks:
        text = (b.get("text") or "").strip()
        if not text:
            continue
        time_line = b.get("time", "")
        if offset_seconds:
            time_line = shift_time_str(time_line, offset_seconds)
        counter += 1
        lines.append(str(counter))
        lines.append(normalize_time_line(time_line, as_vtt=True))
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def apply_translated_blocks(target_blocks: list, parsed: list) -> int:
    """
    Copies translated text onto the ORIGINAL cues without ever touching their timing.

    AI engines regularly merge, drop or split a cue. The old code mapped results by
    position, so a single missing cue shifted every following line onto the wrong
    timestamp for the rest of the chunk. Matching is done by timecode first and by the
    numeric cue id second; unmatched cues simply keep their original text.
    Returns the number of cues that were actually replaced.
    """
    if not parsed:
        return 0

    by_time = {}
    by_index = {}
    for p in parsed:
        key = normalize_time_line(p.get("time", ""))
        if key:
            by_time.setdefault(key, []).append(p)
        pid = (p.get("prefix") or "").strip()
        if re.fullmatch(r"\d+", pid):
            by_index.setdefault(int(pid), p)

    applied = 0
    for pos, b in enumerate(target_blocks):
        match = None
        bucket = by_time.get(normalize_time_line(b.get("time", "")))
        if bucket:
            match = bucket.pop(0)
        elif (pos + 1) in by_index:
            match = by_index.pop(pos + 1)
        if match and (match.get("text") or "").strip():
            b["text"] = match["text"].strip()
            applied += 1
    return applied


def reindex_srt(srt_content: str) -> str:
    _, blocks = parse_subtitles(srt_content)
    lines = []
    for idx, b in enumerate(blocks):
        lines.append(f"{idx + 1}")
        lines.append(f"{b['time']}")
        lines.append(f"{b['text']}")
        lines.append("")
    return "\n".join(lines)


def clean_subtitle_text(text: str) -> str:
    """Removes ASS/SSA override tags and font tags left over after ffmpeg conversion."""
    if not text:
        return ""
    text = re.sub(r"\{\\[^}]*\}", "", text)
    text = re.sub(r"</?font[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\\N|\\n", "\n", text)
    lines = [l.strip() for l in text.split("\n")]
    return "\n".join([l for l in lines if l]).strip()


def clean_extracted_srt(srt_content: str) -> str:
    """Cleans styling tags of an extracted embedded subtitle and drops empty cues."""
    _, blocks = parse_subtitles(srt_content)
    cleaned = []
    for b in blocks:
        text = clean_subtitle_text(b["text"])
        if text:
            cleaned.append({"prefix": "", "time": b["time"], "text": text})
    if not cleaned:
        return ""
    lines = []
    for idx, b in enumerate(cleaned):
        lines.append(f"{idx + 1}")
        lines.append(f"{b['time']}")
        lines.append(f"{b['text']}")
        lines.append("")
    return "\n".join(lines).strip()


def get_banner_block(progress: int) -> dict:
    return {
        "prefix": "1",
        "time": "00:00:00,000 --> 00:00:08,000",
        "text": f"<b>[Phụ đề dịch tự động bằng AI - Tiến trình: {progress}%]</b>"
    }


async def translate_google(text: str, target_lang: str = "vi") -> str:
    url = (
        GOOGLE_TRANSLATE_ENDPOINT
        + "?client=gtx&dt=t&sl=auto&tl=" + urllib.parse.quote(target_lang)
        + "&q=" + urllib.parse.quote(text)
    )
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            translated = "".join([item[0] for item in data[0] if item[0]])
            return translated
        else:
            raise Exception(f"Google Translate API status {resp.status_code}")


def get_gemini_endpoint(api_key: str, model: str = None) -> str:
    """Builds the Gemini generateContent endpoint without any f-string braces."""
    model = model or Config.GEMINI_MODEL
    return GEMINI_API_BASE + str(model) + ":generateContent?key=" + str(api_key)


async def translate_gemini(text: str, api_key: str, target_lang: str = "vi") -> str:
    url = get_gemini_endpoint(api_key)
    prompt = (
        "Translate the following subtitles into natural, conversational Vietnamese. "
        "Keep all timestamps, line numbers, and formatting exactly as they are. "
        "Never merge, split, drop or reorder subtitle blocks: return exactly one block "
        "per input block, with the same number and the same timestamp line. "
        "Output only the translated SRT subtitles and nothing else:\n\n" + text
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
        "Translate the following subtitles into natural, conversational Vietnamese. "
        "Keep all timestamps, line numbers, and formatting exactly as they are. "
        "Never merge, split, drop or reorder subtitle blocks: return exactly one block "
        "per input block, with the same number and the same timestamp line. "
        "Output only the translated SRT subtitles and nothing else:\n\n" + text
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
        min_aligned = max(1, int(len(chunk) * 0.8))

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

                candidate = [dict(b) for b in chunk]
                applied = apply_translated_blocks(candidate, parsed_chunk)
                if applied >= min_aligned:
                    translated_blocks.extend(candidate)
                    success = True
                    logger.info(f"Batch {i//batch_size + 1} translated via Custom AI ({applied}/{len(chunk)} cues aligned).")
                else:
                    logger.warning(f"Custom AI aligned only {applied}/{len(chunk)} cues for batch {i//batch_size + 1}.")
            except Exception as e:
                logger.error(f"Custom AI translation failed for batch {i//batch_size + 1}: {e}.")

        # 2. Try Gemini API if Custom AI is not configured or failed
        if not success and api_key:
            try:
                logger.info(f"Falling back to Gemini API (Model: {Config.GEMINI_MODEL}) for batch {i//batch_size + 1}...")
                translated_srt = await translate_gemini(chunk_srt, api_key, target_lang)
                _, parsed_chunk = parse_subtitles(translated_srt)

                candidate = [dict(b) for b in chunk]
                applied = apply_translated_blocks(candidate, parsed_chunk)
                if applied >= min_aligned:
                    translated_blocks.extend(candidate)
                    success = True
                    logger.info(f"Batch {i//batch_size + 1} translated via Gemini ({applied}/{len(chunk)} cues aligned).")
                else:
                    logger.warning(f"Gemini aligned only {applied}/{len(chunk)} cues for batch {i//batch_size + 1}. Falling back to Google Translate.")
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


def get_remote_input_opts(video_url: str) -> list:
    """HTTP options so ffmpeg/ffprobe survive debrid/Telegram stream hiccups and UA checks."""
    if not video_url or not str(video_url).lower().startswith(("http://", "https://")):
        return []
    return [
        "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
    ]


def select_embedded_subtitle_stream(streams: list, prefer_langs: tuple = ("eng", "en")) -> Optional[dict]:
    """
    Picks the best TEXT based subtitle stream.
    Bitmap streams (PGS/DVD/DVB/XSUB) are skipped because ffmpeg cannot convert them to SRT.
    Forced / signs-only tracks are de-prioritized because they contain just a handful of cues.
    """
    text_streams = []
    unknown_streams = []

    for rel_idx, s in enumerate(streams):
        codec = (s.get("codec_name") or "").lower()
        tags = s.get("tags") or {}
        disposition = s.get("disposition") or {}
        entry = {
            "abs_index": s.get("index"),
            "rel_index": rel_idx,
            "codec": codec,
            "lang": (tags.get("language") or "").lower(),
            "title": (tags.get("title") or "").lower(),
            "forced": int(disposition.get("forced", 0) or 0),
            "hearing_impaired": int(disposition.get("hearing_impaired", 0) or 0),
        }
        if codec in IMAGE_SUB_CODECS:
            logger.info(f"Skipping bitmap subtitle stream {entry['abs_index']} ({codec}) - cannot be converted to text.")
            continue
        if codec in TEXT_SUB_CODECS:
            text_streams.append(entry)
        else:
            unknown_streams.append(entry)

    candidates = text_streams or unknown_streams
    if not candidates:
        return None

    def score(entry: dict) -> float:
        value = 0.0
        if entry["lang"] in prefer_langs or "english" in entry["title"] or "eng" in entry["title"]:
            value -= 100.0
        if entry["forced"] or "forced" in entry["title"] or "signs" in entry["title"] or "songs" in entry["title"]:
            value += 60.0
        if entry["hearing_impaired"] or "sdh" in entry["title"]:
            value += 5.0
        value += entry["rel_index"] * 0.1
        return value

    return sorted(candidates, key=score)[0]


async def _ffmpeg_extract_stream(video_url: str, map_arg: str, timeout: int = 180) -> Optional[str]:
    """Runs ffmpeg to extract one subtitle stream to SRT. Returns raw SRT text or None."""
    ffmpeg_bin = get_ffmpeg_path()
    fd, tmp_srt_path = tempfile.mkstemp(suffix=".srt", dir=CACHE_DIR)
    os.close(fd)

    cmd_extract = [
        ffmpeg_bin, "-y",
        "-nostdin",
        *get_remote_input_opts(video_url),
        "-analyzeduration", "100000000",
        "-probesize", "100000000",
        "-i", video_url,
        "-map", map_arg,
        "-c:s", "subrip",
        "-f", "srt",
        tmp_srt_path
    ]

    logger.info(f"Running ffmpeg extraction for stream {map_arg}...")
    try:
        def run_extract():
            return subprocess.run(cmd_extract, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        extract_res = await asyncio.to_thread(run_extract)

        srt_content = None
        if os.path.exists(tmp_srt_path) and os.path.getsize(tmp_srt_path) > 10:
            with open(tmp_srt_path, "r", encoding="utf-8", errors="ignore") as f:
                srt_content = f.read()

        if srt_content and srt_content.strip():
            return srt_content.strip()

        err_output = extract_res.stderr.decode("utf-8", errors="ignore") if extract_res and extract_res.stderr else ""
        logger.warning(f"ffmpeg extraction of {map_arg} yielded no data (code {extract_res.returncode}). Stderr tail: {err_output[-500:]}")
    except subprocess.TimeoutExpired:
        logger.warning(f"ffmpeg extraction of {map_arg} timed out after {timeout}s.")
    except Exception as e:
        logger.warning(f"ffmpeg extraction of {map_arg} raised: {e}")
    finally:
        if os.path.exists(tmp_srt_path):
            try:
                os.remove(tmp_srt_path)
            except Exception:
                pass
    return None


async def extract_embedded_subtitle(video_url: str, prefer_langs: tuple = ("eng", "en")) -> Optional[str]:
    """
    Inspects video_url using ffprobe for embedded subtitle streams.
    Extracts the best matching TEXT subtitle stream (English or first available) to SRT format.
    Returns cleaned SRT content string, or None if no text subtitle stream found/extracted.
    """
    if not video_url:
        return None

    ffprobe_bin = get_ffprobe_path()
    cmd_probe = [
        ffprobe_bin,
        "-v", "error",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "s",
        *get_remote_input_opts(video_url),
        "-analyzeduration", "100000000",
        "-probesize", "100000000",
        video_url
    ]

    logger.info(f"Running ffprobe to detect embedded subtitles on {str(video_url)[:120]}...")
    try:
        def run_probe():
            return subprocess.run(cmd_probe, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90)

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

        chosen = select_embedded_subtitle_stream(streams, prefer_langs)
        if not chosen:
            logger.warning(
                "Only bitmap (PGS/DVD/DVB) subtitle streams are embedded in this video; "
                "they cannot be converted to text. Falling back to other subtitle sources."
            )
            return None

        logger.info(
            f"Selected embedded subtitle stream index {chosen['abs_index']} "
            f"(codec={chosen['codec']}, lang={chosen['lang']}, title={chosen['title']}, forced={chosen['forced']})."
        )

        # Try absolute stream index first, then the relative subtitle index (0:s:N) as a retry.
        srt_content = None
        if chosen.get("abs_index") is not None:
            srt_content = await _ffmpeg_extract_stream(video_url, f"0:{chosen['abs_index']}")
        if not srt_content:
            srt_content = await _ffmpeg_extract_stream(video_url, f"0:s:{chosen['rel_index']}")

        if not srt_content:
            logger.warning("Embedded subtitle extraction produced no usable SRT content.")
            return None

        cleaned = clean_extracted_srt(srt_content)
        if not cleaned:
            logger.warning("Extracted embedded subtitle contained no text cues after cleaning.")
            return None

        logger.info(f"Successfully extracted embedded subtitle ({len(cleaned)} bytes, {len(cleaned.splitlines())} lines).")
        return cleaned

    except subprocess.TimeoutExpired:
        logger.warning("ffprobe timed out while detecting embedded subtitles.")
    except Exception as e:
        logger.warning(f"Failed to extract embedded subtitle: {e}")

    return None
