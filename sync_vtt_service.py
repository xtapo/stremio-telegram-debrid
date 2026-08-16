"""
Progressive (partial result) Vietnamese VTT generation for the Stremio /subtitles endpoint.

Stremio blocks while it waits for the subtitle response, so translating a whole movie
inline (1500+ cues) makes the client time out and show "no subtitles" even though the
backend is still working. The work is therefore split into two passes:

  1. head pass  - the first SYNC_VTT_HEAD_SECONDS (default 300s = 5 minutes) of the movie
                  are translated inline with the FASTEST engine order and returned right
                  away, so playback starts with Vietnamese subtitles almost immediately.
  2. background - the rest of the movie is translated slice by slice in a background task
                  with the QUALITY engine order. Every following /subtitles request serves
                  whatever is ready so far plus a progress banner, and the finished track
                  is written to the disk cache.

Engine order (configurable through the constants below):
  fast pass       : Lingva -> Gemini -> Custom AI     (latency matters most)
  background pass : Custom AI -> Gemini -> Google Translate  (quality matters most)
"""
import os
import re
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


# How much of the movie is translated inline before answering Stremio.
HEAD_WINDOW_SECONDS = _read_number("SYNC_VTT_HEAD_SECONDS", 300.0)
# Hard cap so a very dense subtitle file cannot block the response either.
HEAD_MAX_BLOCKS = int(_read_number("SYNC_VTT_HEAD_MAX_BLOCKS", 400))
# Size of one background slice: smaller = partial results appear more often.
BACKGROUND_SLICE = int(_read_number("SYNC_VTT_BACKGROUND_SLICE", 150))

FAST_ENGINE_ORDER = ("lingva", "gemini", "custom")
BACKGROUND_ENGINE_ORDER = ("custom", "gemini", "google")

LINGVA_INSTANCES = [
    "https://lingva.ml",
    "https://lingva.garudalinux.org",
    "https://translate.plausibility.cloud",
]

# Chunk size / concurrency per engine. Lingva used to fire every chunk at once, which
# got the public instances to rate limit us on long movies, hence the semaphore.
LINGVA_BATCH = 40
LINGVA_CONCURRENCY = 4
GEMINI_CHUNK = 150
GEMINI_CONCURRENCY = 2
CUSTOM_CHUNK = 100
CUSTOM_CONCURRENCY = 2
GOOGLE_BATCH = 30
GOOGLE_CONCURRENCY = 3

# A cue is considered translated when at least this share of the batch changed.
MIN_TRANSLATED_RATIO = 0.5

# In-memory mapping of item_id -> active stream video_url (registered by addon.py).
STREAM_VIDEO_URL_CACHE = {}

# clean_id -> {"blocks", "head_count", "progress", "done", "translated_ok", "source", "task"}
SYNC_VTT_TASKS = {}
_SYNC_VTT_LOCKS = {}


def _get_lock(clean_id: str) -> asyncio.Lock:
    lock = _SYNC_VTT_LOCKS.get(clean_id)
    if lock is None:
        lock = asyncio.Lock()
        _SYNC_VTT_LOCKS[clean_id] = lock
    return lock


def _strip_code_fence(text: str) -> str:
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
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


async def _engine_ai(blocks: list, chunk_size: int, concurrency: int, call, label: str):
    """Shared implementation for the SRT-in / SRT-out AI engines (Gemini, Custom AI)."""
    chunks = [blocks[i:i + chunk_size] for i in range(0, len(blocks), chunk_size)]
    sem = asyncio.Semaphore(concurrency)

    async def run_chunk(chunk_blocks):
        async with sem:
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

    results = await asyncio.gather(*[run_chunk(c) for c in chunks], return_exceptions=True)
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


async def _run_engine(name: str, blocks: list, target_lang: str):
    if name == "lingva":
        await _engine_lingva(blocks, target_lang)
        return
    if name == "gemini":
        api_key = Config.GEMINI_API_KEY
        if not api_key:
            raise Exception("GEMINI_API_KEY is not configured")
        await _engine_ai(
            blocks,
            GEMINI_CHUNK,
            GEMINI_CONCURRENCY,
            lambda raw: translate_gemini(raw, api_key, target_lang),
            "Gemini",
        )
        return
    if name == "custom":
        if not Config.CUSTOM_AI_API_URL:
            raise Exception("CUSTOM_AI_API_URL is not configured")
        await _engine_ai(
            blocks,
            CUSTOM_CHUNK,
            CUSTOM_CONCURRENCY,
            lambda raw: translate_custom_ai(raw, target_lang),
            "Custom AI",
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
) -> bool:
    """
    Translates cues in place, trying each engine in order until one succeeds.
    A partially translated batch is rolled back before the next engine runs, so an
    engine never translates text that another engine already translated.
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
            await _run_engine(name, blocks, target_lang)
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

    logger.error("All translation engines failed for this batch.")
    return False


async def translate_srt_fast_batch(
    srt_content: str,
    target_lang: str = "vi",
    return_status: bool = False,
    engine_order: tuple = None,
):
    """
    Translates a whole SRT/VTT document at once and returns a valid WebVTT string.
    Kept for callers/tests that want the blocking behaviour; the Stremio endpoint uses
    the progressive get_or_generate_synced_vtt below instead.
    """
    _, blocks = parse_subtitles(srt_content)
    if not blocks:
        return (srt_content, False) if return_status else srt_content

    order = tuple(engine_order) if engine_order else FAST_ENGINE_ORDER + ("google",)
    ok = await translate_block_list(blocks, order, target_lang)
    content = build_vtt(blocks, SUBTITLE_TIME_OFFSET)
    return (content, ok) if return_status else content


# ---------------------------------------------------------------------------
# Base subtitle lookup
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


# ---------------------------------------------------------------------------
# Progressive flow
# ---------------------------------------------------------------------------

def _block_start_seconds(block: dict) -> float:
    time_line = block.get("time") or ""
    if "-->" not in time_line:
        return 0.0
    return parse_time_to_seconds(time_line.split("-->", 1)[0])


def _head_block_count(blocks: list) -> int:
    """Number of cues that fall inside the inline (fast) translation window."""
    count = 0
    for b in blocks:
        if _block_start_seconds(b) < HEAD_WINDOW_SECONDS:
            count += 1
        else:
            break
    return max(1, min(count or 1, HEAD_MAX_BLOCKS, len(blocks)))


def _render_state(state: dict) -> str:
    blocks = state["blocks"]
    if state.get("done"):
        return build_vtt(blocks, SUBTITLE_TIME_OFFSET)

    percent = int(state.get("progress", 0.0) * 100)
    banner = {
        "prefix": "",
        "time": "00:00:00,000 --> 00:00:08,000",
        "text": (
            f"<b>[Đang dịch phần còn lại bằng AI: {percent}% "
            "- tải lại phụ đề sau vài phút để có bản đầy đủ]</b>"
        ),
    }
    return build_vtt([banner] + blocks, SUBTITLE_TIME_OFFSET)


def _write_cache(cache_file: str, content: str) -> bool:
    try:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        logger.warning(f"Failed to write cache for {cache_file}: {e}")
        return False


async def _translate_remaining(clean_id: str, cache_file: str, target_lang: str = "vi"):
    """Background pass: translates everything after the head window, slice by slice."""
    state = SYNC_VTT_TASKS.get(clean_id)
    if not state:
        return

    blocks = state["blocks"]
    total = len(blocks)
    start = state["head_count"]
    translated_ok = state.get("translated_ok", False)

    try:
        for i in range(start, total, BACKGROUND_SLICE):
            slice_blocks = blocks[i:i + BACKGROUND_SLICE]
            logger.info(
                f"Background translation for {clean_id}: cues {i + 1}-{i + len(slice_blocks)}/{total}..."
            )
            ok = await translate_block_list(slice_blocks, BACKGROUND_ENGINE_ORDER, target_lang)
            translated_ok = translated_ok or ok
            state["progress"] = min(0.99, (i + len(slice_blocks)) / max(1, total))

        state["progress"] = 1.0
        state["translated_ok"] = translated_ok
        state["done"] = True

        # Never cache an untranslated track, otherwise the English text sticks around forever.
        if translated_ok:
            if _write_cache(cache_file, build_vtt(blocks, SUBTITLE_TIME_OFFSET)):
                logger.info(f"Background translation finished and cached for {clean_id}.")
                SYNC_VTT_TASKS.pop(clean_id, None)
        else:
            logger.warning(f"Background translation produced nothing usable for {clean_id}; not cached.")
    except Exception as e:
        logger.error(f"Background translation for {clean_id} failed: {e}")
        state["done"] = True


async def get_or_generate_synced_vtt(
    media_type: str, item_id: str, video_url: Optional[str] = None
) -> Optional[str]:
    """
    Returns a Vietnamese WebVTT track for this item, WITHOUT making Stremio wait for the
    whole movie: the first few minutes are translated inline, the rest keeps translating
    in the background and is served progressively on the following requests.
    """
    clean_id = item_id.replace(":", "_").replace("/", "_")
    cache_file = os.path.join(CACHE_DIR, f"vi_sync_{clean_id}.vtt")

    def read_cache() -> Optional[str]:
        if os.path.exists(cache_file) and os.path.getsize(cache_file) > 100:
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                return None
        return None

    cached = read_cache()
    if cached:
        return cached

    async with _get_lock(clean_id):
        # Another request may have finished the whole job while we waited for the lock.
        cached = read_cache()
        if cached:
            return cached

        state = SYNC_VTT_TASKS.get(clean_id)
        if state:
            return _render_state(state)

        base_srt, base_source = await _load_base_subtitle(media_type, item_id, clean_id, video_url)
        if not base_srt:
            return None

        _, blocks = parse_subtitles(base_srt)
        if not blocks:
            logger.warning(f"Base subtitle for {item_id} (source={base_source}) contained no cues.")
            return None

        head_count = _head_block_count(blocks)
        logger.info(
            f"Translating the first {head_count}/{len(blocks)} cues inline "
            f"(source={base_source}, engines={'/'.join(FAST_ENGINE_ORDER)})..."
        )
        # blocks[:head_count] shares the same dicts as blocks, so this updates them in place.
        head_ok = await translate_block_list(blocks[:head_count], FAST_ENGINE_ORDER, "vi")

        state = {
            "blocks": blocks,
            "head_count": head_count,
            "progress": head_count / max(1, len(blocks)),
            "done": head_count >= len(blocks),
            "translated_ok": head_ok,
            "source": base_source,
        }
        SYNC_VTT_TASKS[clean_id] = state

        if head_count >= len(blocks):
            state["progress"] = 1.0
            content = build_vtt(blocks, SUBTITLE_TIME_OFFSET)
            if head_ok and _write_cache(cache_file, content):
                SYNC_VTT_TASKS.pop(clean_id, None)
            return content

        state["task"] = asyncio.create_task(_translate_remaining(clean_id, cache_file))
        logger.info(
            f"Serving the first {head_count} cues now; the remaining "
            f"{len(blocks) - head_count} cues are translated in the background "
            f"(engines={'/'.join(BACKGROUND_ENGINE_ORDER)})."
        )
        return _render_state(state)
