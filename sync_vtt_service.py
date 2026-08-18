"""
Two Vietnamese subtitle tracks for the Stremio /subtitles endpoint.

Track 1 - "fast" (the default track, listed first in Stremio):
    Lingva translates the WHOLE subtitle file in parallel and the result is
    returned inline. No banner and no second pass: what you see is the final
    text of that track. Google Translate is only a safety net for when every
    Lingva instance refuses the batch.

Track 2 - "quality" (translated in the background):
    Gemini first, Custom AI second. The whole file is handed to the engine in
    ONE pass, which internally splits it into chunks that run in parallel, so
    the upgrade lands roughly three times faster than the old slice-by-slice
    loop. Every chunk that lands reports back, so the progress banner keeps
    moving. Cues that Gemini has not reached yet are served with the Lingva
    text from track 1, so track 2 reads as Vietnamese from the first second.

Both tracks share one base subtitle (embedded track or OpenSubtitles), so the
expensive ffmpeg extraction only happens once per item.
"""
import os
import re
import time
import httpx
import urllib.parse
import asyncio
import logging
from typing import Optional
from config import Config

from subtitle_utils import (
    CACHE_DIR,
    OPENSUBTITLES_BASE,
    SUBTITLE_TIME_OFFSET,
    apply_translated_blocks,
    build_srt,
    build_vtt,
    extract_embedded_subtitle,
    parse_subtitles,
    parse_time_to_seconds,
    translate_custom_ai,
    translate_gemini,
    translate_google,
)

logger = logging.getLogger("subtitles_service")


def _read_number(name: str, default: float) -> float:
    """Reads a numeric setting from Config first, then from the environment."""
    try:
        raw = getattr(Config, name, None)
        if raw in (None, ""):
            raw = os.getenv(name)
        if raw in (None, ""):
            return float(default)
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _read_flag(name: str, default: bool) -> bool:
    raw = getattr(Config, name, None)
    if raw in (None, ""):
        raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Engine order per track
# ---------------------------------------------------------------------------
# Track 1: Fast track using Gemini, Custom AI, and Lingva (no Google Translate)
def get_fast_engine_order() -> tuple:
    engines = []
    if getattr(Config, "ENABLE_GEMINI", True) and Config.GEMINI_API_KEY:
        engines.append("gemini")
    if getattr(Config, "ENABLE_CUSTOM_AI", True) and Config.CUSTOM_AI_API_URL:
        engines.append("custom")
    engines.append("lingva")
    return tuple(engines)


# Track 2: quality matters most. Gemini uses Config.GEMINI_MODEL.
def get_quality_engine_order() -> tuple:
    engines = []
    if getattr(Config, "ENABLE_GEMINI", True) and Config.GEMINI_API_KEY:
        engines.append("gemini")
    if getattr(Config, "ENABLE_CUSTOM_AI", True) and Config.CUSTOM_AI_API_URL:
        engines.append("custom")
    if not engines:
        engines.append("lingva")
    return tuple(engines)


FAST_ENGINE_ORDER = ("gemini", "custom", "lingva")
QUALITY_ENGINE_ORDER = ("gemini", "custom")
# Older callers imported this name; keep it pointing at the background order.
BACKGROUND_ENGINE_ORDER = QUALITY_ENGINE_ORDER


# ---------------------------------------------------------------------------
# Locks and in-flight tracking
# ---------------------------------------------------------------------------
_FAST_LOCKS = {}
_QUALITY_LOCKS = {}
_BASE_LOCKS = {}
_BASE_SUBS = {}
_FAST_BLOCKS = {}
SYNC_VTT_TASKS = {}
STREAM_VIDEO_URL_CACHE = {}


def _get_lock(locks: dict, clean_id: str) -> asyncio.Lock:
    if clean_id not in locks:
        locks[clean_id] = asyncio.Lock()
    return locks[clean_id]


def _get_addon_base_url() -> str:
    try:
        from config import Config
        if getattr(Config, "ADDON_URL", None):
            return Config.ADDON_URL.rstrip("/")
        port = getattr(Config, "PORT", 8000)
        return f"http://localhost:{port}"
    except Exception:
        return "http://localhost:8000"


def _log_sub_banner(title: str, clean_id: str, media_type: str, track: str, file_path: str, extra_info: str = ""):
    base_url = _get_addon_base_url()
    srt_download_url = f"{base_url}/subtitles/srt/{clean_id}.srt?type={media_type}&track={track}"
    vtt_download_url = f"{base_url}/subtitles/vtt/{clean_id}.vtt?type={media_type}&track={track}"
    sep = "=" * 80
    lines = [
        "",
        sep,
        f"🎯 {title}: {clean_id}",
        f"   🔗 Link tải file .SRT (Tải về máy xem offline / VLC / PotPlayer):",
        f"      👉 {srt_download_url}",
        f"   🔗 Link tải file .VTT (Xem online / Stremio Web):",
        f"      👉 {vtt_download_url}",
        f"   📁 File lưu tại máy:",
        f"      👉 {file_path}",
    ]
    if extra_info:
        lines.append(f"   ℹ️ {extra_info}")
    lines.append(sep)
    logger.info("\n".join(lines))


# Hand the whole file to the engine at once (chunks still run in parallel).
# Set to False to fall back to the older sequential slice loop.
QUALITY_ONE_PASS = _read_flag("SYNC_VTT_QUALITY_ONE_PASS", True)
# Cues per background slice, only used when QUALITY_ONE_PASS is False.
BACKGROUND_SLICE = int(_read_number("SYNC_VTT_BACKGROUND_SLICE", 150))
# Start track 2 automatically as soon as track 1 finished.
AUTO_START_QUALITY = _read_flag("SYNC_VTT_AUTO_QUALITY", True)

# Kept so existing imports and scratch tests keep working.
HEAD_WINDOW_SECONDS = _read_number("SYNC_VTT_HEAD_SECONDS", 300.0)
HEAD_MAX_BLOCKS = int(_read_number("SYNC_VTT_HEAD_MAX_BLOCKS", 400))

LINGVA_INSTANCES = [
    "https://lingva.ml",
    "https://lingva.garudalinux.org",
    "https://translate.plausibility.cloud",
]

# Chunk size / concurrency per engine. Both tracks translate the whole movie in
# one call now, so these decide how many requests are in flight at once. Lower
# them if the provider starts answering with 429.
LINGVA_BATCH = int(_read_number("SYNC_VTT_LINGVA_BATCH", 40))
LINGVA_CONCURRENCY = int(_read_number("SYNC_VTT_LINGVA_CONCURRENCY", 8))
GEMINI_CHUNK = int(_read_number("SYNC_VTT_GEMINI_CHUNK", 150))
GEMINI_CONCURRENCY = int(_read_number("SYNC_VTT_GEMINI_CONCURRENCY", 4))
CUSTOM_CHUNK = int(_read_number("SYNC_VTT_CUSTOM_CHUNK", 100))
CUSTOM_CONCURRENCY = int(_read_number("SYNC_VTT_CUSTOM_CONCURRENCY", 3))
GOOGLE_BATCH = 30
GOOGLE_CONCURRENCY = 3

# A cue batch counts as translated when at least this share of it changed.
MIN_TRANSLATED_RATIO = 0.5

# In-memory mapping of item_id -> active stream video_url (registered by addon.py).
STREAM_VIDEO_URL_CACHE = {}

# clean_id -> {"blocks", "ready", "fallback", "progress", "done", "translated_ok", "task"}
SYNC_VTT_TASKS = {}
# clean_id -> the Lingva-translated cues of track 1, used as track 2's stand-in text.
_FAST_BLOCKS = {}
# clean_id -> (base_srt, source)
_BASE_SUBS = {}

_FAST_LOCKS = {}
_QUALITY_LOCKS = {}
_BASE_LOCKS = {}
# Old name, kept so existing imports do not break.
_SYNC_VTT_LOCKS = _FAST_LOCKS


def _get_lock(store: dict, key: str) -> asyncio.Lock:
    lock = store.get(key)
    if lock is None:
        lock = asyncio.Lock()
        store[key] = lock
    return lock


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Translation engines. Every engine mutates the cue dicts IN PLACE and never
# touches their "time" field, so timing can not drift no matter what the engine
# returns.
# ---------------------------------------------------------------------------

async def _engine_lingva(blocks: list, target_lang: str):
    chunks = [blocks[i:i + LINGVA_BATCH] for i in range(0, len(blocks), LINGVA_BATCH)]
    sem = asyncio.Semaphore(LINGVA_CONCURRENCY)

    async def run_chunk(chunk_blocks, client):
        tagged = "\n".join(
            f"[[{idx}]] " + b["text"].replace("\n", " ") for idx, b in enumerate(chunk_blocks)
        )
        async with sem:
            for inst in LINGVA_INSTANCES:
                try:
                    url = (
                        inst.rstrip("/")
                        + "/api/v1/auto/"
                        + urllib.parse.quote(target_lang)
                        + "/"
                        + urllib.parse.quote(tagged)
                    )
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    translated = resp.json().get("translation", "")
                    extracted = {}
                    for m in re.finditer(r"\[\s*\[\s*(\d+)\s*\]\s*\]\s*([^\[]+)", translated):
                        extracted[int(m.group(1))] = m.group(2).strip()
                    # Only explicitly tagged indexes are written back, so a dropped line
                    # never shifts the following cues onto the wrong timestamps.
                    for idx, b in enumerate(chunk_blocks):
                        if extracted.get(idx):
                            b["text"] = extracted[idx]
                    return
                except Exception:
                    continue

    async with httpx.AsyncClient(timeout=15.0) as client:
        await asyncio.gather(*[run_chunk(c, client) for c in chunks], return_exceptions=True)


async def _engine_ai(
    blocks: list, chunk_size: int, concurrency: int, call, label: str, on_chunk=None
):
    """Shared implementation for the SRT-in / SRT-out AI engines (Gemini, Custom AI).

    The chunks run in parallel, so the caller can hand over a whole movie in one
    go instead of waiting for slice after slice. `on_chunk(offset, count)` fires
    every time a chunk lands, which is what keeps the track 2 banner moving.
    """
    ranges = [(i, blocks[i:i + chunk_size]) for i in range(0, len(blocks), chunk_size)]
    sem = asyncio.Semaphore(concurrency)

    async def run_chunk(offset: int, chunk_blocks: list):
        chunk_num = offset // chunk_size + 1
        total_chunks = len(ranges)
        async with sem:
            logger.info(f"{label}: translating chunk {chunk_num}/{total_chunks} ({len(chunk_blocks)} cues)...")
            raw = "\n\n".join(
                f"{idx + 1}\n{b['time']}\n{b['text']}" for idx, b in enumerate(chunk_blocks)
            )
            res = _strip_code_fence(await call(raw))
            _, parsed = parse_subtitles(res)
            # Matching is done by timecode / cue id, never by position.
            applied = apply_translated_blocks(chunk_blocks, parsed)
            if applied == 0:
                raise Exception(f"{label} output could not be aligned with the original cues")
            if applied < len(chunk_blocks):
                logger.warning(
                    f"{label} aligned {applied}/{len(chunk_blocks)} cues; the rest keep their original text."
                )
            else:
                logger.info(f"{label}: successfully translated chunk {chunk_num}/{total_chunks} ({applied}/{len(chunk_blocks)} cues).")
            if on_chunk:
                try:
                    on_chunk(offset, len(chunk_blocks))
                except Exception:
                    pass

    results = await asyncio.gather(
        *[run_chunk(offset, chunk) for offset, chunk in ranges], return_exceptions=True
    )
    errors = [r for r in results if isinstance(r, Exception)]
    if errors and len(errors) == len(results):
        raise errors[0]
    for err in errors:
        logger.warning(f"{label} chunk failed: {err}")


async def _engine_google(blocks: list, target_lang: str):
    chunks = [blocks[i:i + GOOGLE_BATCH] for i in range(0, len(blocks), GOOGLE_BATCH)]
    sem = asyncio.Semaphore(GOOGLE_CONCURRENCY)

    def unbr(value: str) -> str:
        return re.sub(r"\s*<\s*br\s*/?\s*>\s*", "\n", value, flags=re.IGNORECASE).strip()

    async def run_chunk(chunk_blocks):
        async with sem:
            joined = "\n".join(b["text"].replace("\n", " <br> ") for b in chunk_blocks)
            try:
                raw = await translate_google(joined, target_lang)
                lines = raw.replace("\r\n", "\n").split("\n")
                if len(lines) > len(chunk_blocks) and not lines[-1].strip():
                    lines.pop()
                if len(lines) == len(chunk_blocks):
                    for b, line in zip(chunk_blocks, lines):
                        text = unbr(line)
                        if text:
                            b["text"] = text
                    return
                logger.warning(
                    f"Google Translate returned {len(lines)} lines for {len(chunk_blocks)} cues; "
                    "falling back to cue-by-cue."
                )
            except Exception as e:
                logger.warning(f"Google Translate batch failed: {e}. Falling back to cue-by-cue.")

            for b in chunk_blocks:
                try:
                    value = await translate_google(b["text"].replace("\n", " <br> "), target_lang)
                    text = unbr(value)
                    if text:
                        b["text"] = text
                except Exception as block_e:
                    logger.error(f"Google Translate failed for a single cue: {block_e}")

    await asyncio.gather(*[run_chunk(c) for c in chunks], return_exceptions=True)


async def _run_engine(name: str, blocks: list, target_lang: str, on_chunk=None):
    if name == "lingva":
        await _engine_lingva(blocks, target_lang)
        return
    if name == "gemini":
        if not getattr(Config, "ENABLE_GEMINI", True):
            raise Exception("Gemini translation is disabled (ENABLE_GEMINI=False)")
        api_key = Config.GEMINI_API_KEY
        if not api_key:
            raise Exception("GEMINI_API_KEY is not configured")
        await _engine_ai(
            blocks,
            GEMINI_CHUNK,
            GEMINI_CONCURRENCY,
            lambda raw: translate_gemini(raw, api_key, target_lang),
            "Gemini",
            on_chunk=on_chunk,
        )
        return
    if name == "custom":
        if not getattr(Config, "ENABLE_CUSTOM_AI", True):
            raise Exception("Custom AI translation is disabled (ENABLE_CUSTOM_AI=False)")
        if not Config.CUSTOM_AI_API_URL:
            raise Exception("CUSTOM_AI_API_URL is not configured")
        await _engine_ai(
            blocks,
            CUSTOM_CHUNK,
            CUSTOM_CONCURRENCY,
            lambda raw: translate_custom_ai(raw, target_lang),
            "Custom AI",
            on_chunk=on_chunk,
        )
        return
    if name == "google":
        await _engine_google(blocks, target_lang)
        return
    raise Exception(f"Unknown translation engine: {name}")


async def translate_block_list(
    blocks: list,
    engine_order: tuple,
    target_lang: str = "vi",
    min_ratio: float = MIN_TRANSLATED_RATIO,
    on_chunk=None,
    on_reset=None,
) -> bool:
    """
    Translates cues in place, trying each engine in order until one succeeds.
    A partially translated batch is rolled back before the next engine runs, so an
    engine never translates text that another engine already translated.

    `on_chunk(offset, count)` reports progress while an engine works, and
    `on_reset()` fires when a batch is rolled back, so the caller can drop the
    progress it recorded for that engine.
    """
    if not blocks:
        return False

    originals = [b["text"] for b in blocks]

    def ratio() -> float:
        changed = sum(
            1 for b, original in zip(blocks, originals) if b["text"].strip() != original.strip()
        )
        return changed / max(1, len(blocks))

    for name in engine_order:
        try:
            logger.info(f"Translating {len(blocks)} cues via {name}...")
            await _run_engine(name, blocks, target_lang, on_chunk=on_chunk)
        except Exception as e:
            logger.warning(f"{name} translation failed: {e}")

        current = ratio()
        if current >= min_ratio:
            logger.info(f"{name} translated {int(current * 100)}% of the cues.")
            return True

        logger.warning(
            f"{name} translated only {int(current * 100)}% of the cues; restoring the original text."
        )
        for b, original in zip(blocks, originals):
            b["text"] = original
        if on_reset:
            try:
                on_reset()
            except Exception:
                pass

    logger.error("All translation engines failed for this batch.")
    return False


async def translate_srt_fast_batch(
    srt_content: str,
    target_lang: str = "vi",
    return_status: bool = False,
    engine_order: tuple = None,
):
    """Translates a whole SRT/VTT document at once and returns a valid WebVTT string."""
    _, blocks = parse_subtitles(srt_content)
    if not blocks:
        return (srt_content, False) if return_status else srt_content

    order = tuple(engine_order) if engine_order else get_fast_engine_order()
    ok = await translate_block_list(blocks, order, target_lang)
    content = build_vtt(blocks, SUBTITLE_TIME_OFFSET)
    return (content, ok) if return_status else content


# ---------------------------------------------------------------------------
# Base subtitle lookup (shared by both tracks)
# ---------------------------------------------------------------------------

def _resolve_imdb_id(item_id: str) -> str:
    imdb_id = item_id
    if "_" in imdb_id and ":" not in imdb_id and not imdb_id.startswith("moviesdrive:"):
        parts = imdb_id.split("_")
        if len(parts) >= 3 and parts[0].startswith("tt"):
            imdb_id = f"{parts[0]}:{parts[1]}:{parts[2]}"
        elif len(parts) == 2 and parts[0].startswith("tt"):
            imdb_id = f"{parts[0]}:{parts[1]}"
    return imdb_id


async def _load_base_subtitle(media_type: str, item_id: str, clean_id: str, video_url: str = None) -> tuple:
    """Returns (base_srt, source). The embedded track wins because it always matches this release."""
    target_video_url = (
        video_url
        or STREAM_VIDEO_URL_CACHE.get(item_id)
        or STREAM_VIDEO_URL_CACHE.get(clean_id)
        or STREAM_VIDEO_URL_CACHE.get(item_id.replace("_", ":"))
    )

    if target_video_url:
        try:
            logger.info(f"Extracting embedded subtitle directly from video: {str(target_video_url)[:80]}...")
            embedded_srt = await extract_embedded_subtitle(target_video_url)
            if embedded_srt and len(embedded_srt) > 100:
                return embedded_srt, "embedded"
            logger.info("No usable embedded subtitle track found, falling back to OpenSubtitles.")
        except Exception as e:
            logger.warning(f"Failed to extract embedded subtitle from video: {e}")
    else:
        logger.info(f"No video URL known for {item_id}; skipping embedded subtitle extraction.")

    imdb_id = _resolve_imdb_id(item_id)
    if imdb_id.startswith("moviesdrive:"):
        try:
            from moviesdrive_router import find_imdb_for_moviesdrive_id
            resolved = await find_imdb_for_moviesdrive_id(media_type, item_id)
            if resolved:
                imdb_id = resolved
        except Exception as e:
            logger.warning(f"Failed to resolve IMDb id for {item_id}: {e}")

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
        if not sub_url:
            continue
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                resp = await client.get(sub_url)
                if resp.status_code == 200 and len(resp.text) > 200:
                    return resp.text, "opensubtitles"
        except Exception:
            continue

    return None, None


def _get_addon_base_url() -> str:
    try:
        from config import Config
        if getattr(Config, "ADDON_URL", None):
            return Config.ADDON_URL.rstrip("/")
        port = getattr(Config, "PORT", 8000)
        return f"http://localhost:{port}"
    except Exception:
        return "http://localhost:8000"


def _log_sub_banner(title: str, clean_id: str, media_type: str, track: str, file_path: str, extra_info: str = ""):
    base_url = _get_addon_base_url()
    download_url = f"{base_url}/subtitles/vtt/{clean_id}.vtt?type={media_type}&track={track}"
    sep = "=" * 80
    lines = [
        "",
        sep,
        f"🎯 {title}: {clean_id}",
        f"   🔗 Link tải phụ đề trực tiếp:",
        f"      👉 {download_url}",
        f"   📁 File lưu tại máy:",
        f"      👉 {file_path}",
    ]
    if extra_info:
        lines.append(f"   ℹ️ {extra_info}")
    lines.append(sep)
    logger.info("\n".join(lines))


async def _get_base_subtitle(media_type: str, item_id: str, clean_id: str, video_url: str = None) -> tuple:
    """_load_base_subtitle plus memory and disk caching.

    Both tracks need the same source text, and pulling it means either an ffmpeg
    pass over a remote video or an OpenSubtitles round trip, so it is cached.
    """
    cached = _BASE_SUBS.get(clean_id)
    if cached and cached[0]:
        return cached

    base_file = os.path.join(CACHE_DIR, f"base_{clean_id}.srt")
    async with _get_lock(_BASE_LOCKS, clean_id):
        cached = _BASE_SUBS.get(clean_id)
        if cached and cached[0]:
            return cached

        if os.path.exists(base_file) and os.path.getsize(base_file) > 200:
            try:
                with open(base_file, "r", encoding="utf-8") as f:
                    content = f.read()
                if content.strip():
                    _BASE_SUBS[clean_id] = (content, "cache")
                    _log_sub_banner(
                        "ĐÃ TÁCH PHỤ ĐỀ GỐC (CACHE SẴN CÓ)",
                        clean_id,
                        media_type,
                        "base",
                        base_file,
                        f"Đã nạp {len(content.splitlines())} dòng phụ đề gốc từ cache",
                    )
                    return _BASE_SUBS[clean_id]
            except Exception:
                pass

        base_srt, source = await _load_base_subtitle(media_type, item_id, clean_id, video_url)
        if base_srt:
            _BASE_SUBS[clean_id] = (base_srt, source)
            _write_cache(base_file, base_srt)
            _log_sub_banner(
                f"ĐÃ TÁCH PHỤ ĐỀ GỐC ({source.upper()})",
                clean_id,
                media_type,
                "base",
                base_file,
                f"Đã trích xuất {len(base_srt.splitlines())} dòng phụ đề gốc",
            )
        return base_srt, source


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _block_start_seconds(block: dict) -> float:
    time_line = block.get("time") or ""
    if "-->" not in time_line:
        return 0.0
    return parse_time_to_seconds(time_line.split("-->", 1)[0])


def _head_block_count(blocks: list) -> int:
    """Cues inside HEAD_WINDOW_SECONDS. Only used by older callers/tests now."""
    count = 0
    for b in blocks:
        if _block_start_seconds(b) < HEAD_WINDOW_SECONDS:
            count += 1
        else:
            break
    return max(1, min(count or 1, HEAD_MAX_BLOCKS, len(blocks)))


def _write_cache(cache_file: str, content: str) -> bool:
    try:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        logger.warning(f"Failed to write cache for {cache_file}: {e}")
        return False


def _read_cache(cache_file: str) -> Optional[str]:
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 100:
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None
    return None


def _fast_cache_file(clean_id: str) -> str:
    return os.path.join(CACHE_DIR, f"vi_fast_{clean_id}.vtt")


def _quality_cache_file(clean_id: str) -> str:
    return os.path.join(CACHE_DIR, f"vi_quality_{clean_id}.vtt")


def _clean(item_id: str) -> str:
    return item_id.replace(":", "_").replace("/", "_")


# ---------------------------------------------------------------------------
# Track 1: Lingva over the whole file
# ---------------------------------------------------------------------------

async def get_or_generate_fast_vtt(
    media_type: str, item_id: str, video_url: Optional[str] = None
) -> Optional[str]:
    """Default track: Lingva translates every cue in parallel, then we answer."""
    clean_id = _clean(item_id)
    cache_file = _fast_cache_file(clean_id)

    cached = _read_cache(cache_file)
    if cached:
        _log_sub_banner(
            "PHỤ ĐỀ TIẾNG VIỆT FAST (CACHE SẴN CÓ)",
            clean_id,
            media_type,
            "fast",
            cache_file,
            "Đã sẵn sàng tải xuống từ cache",
        )
        return cached

    async with _get_lock(_FAST_LOCKS, clean_id):
        cached = _read_cache(cache_file)
        if cached:
            return cached

        base_srt, base_source = await _get_base_subtitle(media_type, item_id, clean_id, video_url)
        if not base_srt:
            return None

        _, blocks = parse_subtitles(base_srt)
        if not blocks:
            logger.warning(f"Base subtitle for {item_id} (source={base_source}) contained no cues.")
            return None

        fast_order = get_fast_engine_order()
        started = time.time()
        logger.info(
            f"Track 1: translating all {len(blocks)} cues of {item_id} "
            f"(source={base_source}, engines={'/'.join(fast_order)}, "
            f"concurrency={LINGVA_CONCURRENCY})..."
        )
        ok = await translate_block_list(blocks, fast_order, "vi")
        content = build_vtt(blocks, SUBTITLE_TIME_OFFSET)
        logger.info(
            f"Track 1 finished for {item_id} in {time.time() - started:.1f}s (translated={ok})."
        )

        if ok:
            # Keep the Vietnamese cues around: track 2 shows them for every cue
            # it has not upgraded yet.
            _FAST_BLOCKS[clean_id] = [dict(b) for b in blocks]
            _write_cache(cache_file, content)
            _log_sub_banner(
                "ĐÃ DỊCH PHỤ ĐỀ TIẾNG VIỆT (FAST)",
                clean_id,
                media_type,
                "fast",
                cache_file,
                f"Dịch hoàn tất trong {time.time() - started:.1f}s ({len(blocks)} câu)",
            )
            if AUTO_START_QUALITY:
                _start_quality_task(media_type, item_id, clean_id)

        return content


# ---------------------------------------------------------------------------
# Track 2: Gemini, then Custom AI, in the background
# ---------------------------------------------------------------------------

def _merged_blocks(state: dict) -> list:
    """Upgraded cues where ready, Lingva text everywhere else."""
    blocks = state["blocks"]
    ready = state.get("ready") or []
    fallback = state.get("fallback") or []
    if not fallback:
        return blocks

    merged = []
    for idx, b in enumerate(blocks):
        if idx < len(ready) and ready[idx]:
            merged.append(b)
        elif idx < len(fallback) and fallback[idx]:
            merged.append({"prefix": b.get("prefix", ""), "time": b["time"], "text": fallback[idx]})
        else:
            merged.append(b)
    return merged


def _render_state(state: dict) -> str:
    merged = _merged_blocks(state)
    if state.get("done"):
        return build_vtt(merged, SUBTITLE_TIME_OFFSET)

    percent = int(state.get("progress", 0.0) * 100)
    banner = {
        "prefix": "",
        "time": "00:00:00,000 --> 00:00:08,000",
        "text": (
            f"<b>[Bản AI chất lượng cao: {percent}% "
            "- tải lại phụ đề sau vài phút để có bản đầy đủ]</b>"
        ),
    }
    return build_vtt([banner] + merged, SUBTITLE_TIME_OFFSET)


async def _translate_quality(clean_id: str, cache_file: str, target_lang: str = "vi"):
    """Background pass for track 2: Gemini first, Custom AI second.

    With QUALITY_ONE_PASS the whole file goes to the engine in a single call and
    its chunks run in parallel, which is roughly three times faster than the old
    sequential slice loop. Progress is reported per chunk so the banner still
    moves while it runs.
    """
    state = SYNC_VTT_TASKS.get(clean_id)
    if not state:
        return

    blocks = state["blocks"]
    total = len(blocks)
    started = time.time()
    translated_ok = False

    def mark_ready(offset: int, count: int) -> None:
        for idx in range(offset, min(offset + count, total)):
            state["ready"][idx] = True
        done = sum(1 for r in state["ready"] if r)
        state["progress"] = min(0.99, done / max(1, total))

    def reset_ready() -> None:
        # The engine underperformed and its text was rolled back, so the progress
        # recorded for it has to go as well.
        for idx in range(total):
            state["ready"][idx] = False
        state["progress"] = 0.0

    quality_order = get_quality_engine_order()
    try:
        if QUALITY_ONE_PASS:
            logger.info(
                f"Track 2 for {clean_id}: all {total} cues in one pass "
                f"via {'/'.join(quality_order)} "
                f"(chunk={GEMINI_CHUNK}, concurrency={GEMINI_CONCURRENCY})..."
            )
            translated_ok = await translate_block_list(
                blocks,
                quality_order,
                target_lang,
                on_chunk=mark_ready,
                on_reset=reset_ready,
            )
            # An engine that does not report chunks still translated everything.
            if translated_ok and not any(state["ready"]):
                for idx in range(total):
                    state["ready"][idx] = True
        else:
            for i in range(0, total, BACKGROUND_SLICE):
                slice_blocks = blocks[i:i + BACKGROUND_SLICE]
                logger.info(
                    f"Track 2 for {clean_id}: cues {i + 1}-{i + len(slice_blocks)}/{total} "
                    f"via {'/'.join(quality_order)}..."
                )
                ok = await translate_block_list(slice_blocks, quality_order, target_lang)
                if ok:
                    translated_ok = True
                    mark_ready(i, len(slice_blocks))

        state["progress"] = 1.0
        state["translated_ok"] = translated_ok
        state["done"] = True
        upgraded = sum(1 for r in state["ready"] if r)

        # Never cache a track that no engine could translate.
        if translated_ok:
            if _write_cache(cache_file, build_vtt(_merged_blocks(state), SUBTITLE_TIME_OFFSET)):
                logger.info(
                    f"Track 2 finished and cached for {clean_id} in {time.time() - started:.1f}s "
                    f"({upgraded}/{total} cues upgraded by AI)."
                )
                _log_sub_banner(
                    "ĐÃ DỊCH PHỤ ĐỀ TIẾNG VIỆT (AI QUALITY / GEMINI)",
                    clean_id,
                    state.get("media_type") or "movie",
                    "quality",
                    cache_file,
                    f"Nâng cấp AI hoàn tất trong {time.time() - started:.1f}s ({upgraded}/{total} câu)",
                )
                SYNC_VTT_TASKS.pop(clean_id, None)
        else:
            logger.warning(f"Track 2 produced nothing usable for {clean_id}; not cached.")
    except Exception as e:
        logger.error(f"Track 2 for {clean_id} failed: {e}")
        state["done"] = True


async def _prepare_quality_state(
    media_type: str, item_id: str, clean_id: str, video_url: Optional[str] = None
) -> Optional[dict]:
    """Creates the track 2 state and starts its background task."""
    base_srt, base_source = await _get_base_subtitle(media_type, item_id, clean_id, video_url)
    if not base_srt:
        return None

    _, blocks = parse_subtitles(base_srt)
    if not blocks:
        logger.warning(f"Base subtitle for {item_id} (source={base_source}) contained no cues.")
        return None

    # Gemini always translates from the original text; the Lingva result is only
    # used as the stand-in for cues it has not reached yet.
    fast_blocks = _FAST_BLOCKS.get(clean_id) or []
    fallback = (
        [b.get("text", "") for b in fast_blocks] if len(fast_blocks) == len(blocks) else []
    )

    state = {
        "blocks": blocks,
        "ready": [False] * len(blocks),
        "fallback": fallback,
        "progress": 0.0,
        "done": False,
        "translated_ok": False,
        "source": base_source,
        "media_type": media_type,
        "item_id": item_id,
    }
    SYNC_VTT_TASKS[clean_id] = state
    state["task"] = asyncio.create_task(
        _translate_quality(clean_id, _quality_cache_file(clean_id))
    )
    logger.info(
        f"Track 2 started for {item_id}: {len(blocks)} cues, "
        f"{'with' if fallback else 'without'} a Lingva stand-in."
    )
    return state


def _start_quality_task(media_type: str, item_id: str, clean_id: str) -> None:
    """Fire track 2 off in the background, ignoring the result."""
    if clean_id in SYNC_VTT_TASKS or _read_cache(_quality_cache_file(clean_id)):
        return

    async def runner():
        try:
            async with _get_lock(_QUALITY_LOCKS, clean_id):
                if clean_id in SYNC_VTT_TASKS or _read_cache(_quality_cache_file(clean_id)):
                    return
                await _prepare_quality_state(media_type, item_id, clean_id)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Could not start track 2 for {item_id}: {e}")

    try:
        asyncio.create_task(runner())
    except RuntimeError:
        pass


async def get_or_generate_quality_vtt(
    media_type: str, item_id: str, video_url: Optional[str] = None
) -> Optional[str]:
    """Second track: served progressively while Gemini / Custom AI work through it."""
    clean_id = _clean(item_id)
    cache_file = _quality_cache_file(clean_id)

    cached = _read_cache(cache_file)
    if cached:
        _log_sub_banner(
            "PHỤ ĐỀ TIẾNG VIỆT AI QUALITY (CACHE SẴN CÓ)",
            clean_id,
            media_type,
            "quality",
            cache_file,
            "Đã sẵn sàng tải xuống từ cache",
        )
        return cached

    async with _get_lock(_QUALITY_LOCKS, clean_id):
        cached = _read_cache(cache_file)
        if cached:
            return cached

        state = SYNC_VTT_TASKS.get(clean_id)
        if state:
            return _render_state(state)

        state = await _prepare_quality_state(media_type, item_id, clean_id, video_url)
        if not state:
            return None
        return _render_state(state)


# ---------------------------------------------------------------------------
# Compatibility
# ---------------------------------------------------------------------------

async def get_or_generate_synced_vtt(
    media_type: str, item_id: str, video_url: Optional[str] = None
) -> Optional[str]:
    """The default track. Kept under the old name for addon.py and the tests."""
    return await get_or_generate_fast_vtt(media_type, item_id, video_url)


async def get_track_vtt(
    media_type: str, item_id: str, track: str = "fast", video_url: Optional[str] = None
) -> Optional[str]:
    """Dispatch helper used by the /subtitles/vtt endpoint."""
    from config import Config
    if not getattr(Config, "ENABLE_SUBTITLES", True):
        return None

    t = (track or "fast").lower()
    if t in ("quality", "ai", "gemini", "2"):
        if not getattr(Config, "AUTO_VIET_SUB", True):
            return None
        return await get_or_generate_quality_vtt(media_type, item_id, video_url)
    elif t in ("base", "raw", "original", "extracted", "eng", "en"):
        clean_id = _clean(item_id)
        base_srt, _ = await _get_base_subtitle(media_type, item_id, clean_id, video_url)
        if base_srt:
            _, blocks = parse_subtitles(base_srt)
            return build_vtt(blocks, SUBTITLE_TIME_OFFSET) if blocks else base_srt
        return None
    
    if not getattr(Config, "AUTO_VIET_SUB", True):
        return None
    return await get_or_generate_fast_vtt(media_type, item_id, video_url)


async def get_track_srt(
    media_type: str, item_id: str, track: str = "base", video_url: Optional[str] = None
) -> Optional[str]:
    """Dispatch helper used by the /subtitles/srt endpoint to return standard SRT format."""
    from config import Config
    if not getattr(Config, "ENABLE_SUBTITLES", True):
        return None
    clean_id = _clean(item_id)
    t = (track or "base").lower()
    if t in ("base", "raw", "original", "extracted", "eng", "en"):
        base_srt, _ = await _get_base_subtitle(media_type, item_id, clean_id, video_url)
        if base_srt:
            return base_srt
        return None

    vtt_content = await get_track_vtt(media_type, item_id, track, video_url)
    if not vtt_content:
        return None
    _, blocks = parse_subtitles(vtt_content)
    if blocks:
        return build_srt(blocks)
    return vtt_content
