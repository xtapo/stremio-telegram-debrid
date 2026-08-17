"""
FastAPI router for the MoviesDrive addon.

The scraping logic now lives in three modules:

* moviesdrive_perf     - shared HTTP client, cache, mirror racing, prewarm
* moviesdrive_resolver - post pages, archive pages, hubcloud, direct CDN links
* moviesdrive_catalog  - catalog, meta, cinemeta, opensubtitles, id mapping

The important change is that /stream no longer walks the whole
post -> archive -> hubcloud -> gamerxyt chain for every quality. It answers
from the post page alone and hands out /moviesdrive/resolve links, which
resolve the single chosen stream on Play and answer with a 302 redirect.
The top candidates are resolved in the background while the user is still
looking at the list, so the redirect is normally served straight from cache.

Subtitles are offered as two separate Vietnamese tracks (see sync_vtt_service):
track "fast" is Lingva over the whole file and is the default, track "quality"
is the Gemini -> Custom AI pass that keeps improving in the background. They
have different URLs on purpose, so switching track in Stremio really downloads
the other file instead of reusing the cached one.

Every public name of the old module is re-exported here, so importers such as
addon.py and sync_vtt_service.py keep working unchanged.
"""

import asyncio
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse

import moviesdrive_perf as perf
from moviesdrive_perf import (  # noqa: F401  (re-exported for compatibility)
    CACHE,
    CACHE_TTL,
    STREAM_CACHE_TTL,
    cache_stats,
    get_cached,
    save_cache,
    set_cached,
)
import moviesdrive_resolver as resolver
from moviesdrive_resolver import (  # noqa: F401
    HEADERS,
    MOVIESDRIVE_BACKUP_URLS,
    MOVIESDRIVE_BASE_URL,
    collect_candidates,
    current_base,
    fetch_html,
    parse_quality_badge,
    quality_rank,
    resolve_all_download_buttons_from_post,
    resolve_archive_page_episodes,
    resolve_candidate,
    resolve_direct_stream_links,
    resolve_hubcloud_files_from_url,
    resolve_playable_url,
    warm_candidates,
)
import moviesdrive_catalog as catalog
from moviesdrive_catalog import (  # noqa: F401
    CATEGORIES_MAP,
    CINEMETA_API,
    GENRE_OPTIONS,
    fetch_opensubtitles,
    find_imdb_for_moviesdrive_id,
    get_catalog_items,
    get_cinemeta_title,
    get_meta_object,
    search_moviesdrive_api,
)

logger = logging.getLogger("moviesdrive_addon")

moviesdrive_router = APIRouter(prefix="", tags=["moviesdrive"])

GAMERXYT_REFERER = "https://gamerxyt.com/"

# Query value -> Stremio track. Keep these in sync with sync_vtt_service.get_track_vtt.
TRACK_FAST = "fast"
TRACK_QUALITY = "quality"


class SafeStreamingResponse(StreamingResponse):
    async def __call__(self, scope, receive, send) -> None:
        async def safe_send(message):
            try:
                await send(message)
            except RuntimeError as e:
                err_str = str(e)
                if "shorter than Content-Length" in err_str or "longer than Content-Length" in err_str:
                    return
                raise e
            except Exception:
                return

        try:
            await super().__call__(scope, receive, safe_send)
        except RuntimeError as e:
            err_str = str(e)
            if "shorter than Content-Length" in err_str or "longer than Content-Length" in err_str:
                return
            raise e
        except Exception:
            return


# ------------------------------------------------------------------
# Manifest
# ------------------------------------------------------------------
def get_moviesdrive_manifest() -> Dict[str, Any]:
    from config import Config
    show_on_board = getattr(Config, "ENABLE_BOARD_MOVIESDRIVE", True)
    main_req = not show_on_board

    return {
        "id": "com.stremio.moviesdrive.addon",
        "version": "1.2.0",
        "name": "MoviesDrive - 4K Movies & Series",
        "description": "Watch Hollywood, Bollywood, Dual Audio 4K UHD, 1080p, 720p Movies & TV Series from MoviesDrive with fast streaming.",
        "resources": [
            "catalog",
            {"name": "meta", "types": ["movie", "series"], "idPrefixes": ["moviesdrive:", "tt"]},
            {"name": "stream", "types": ["movie", "series"], "idPrefixes": ["moviesdrive:", "tt"]},
            {"name": "subtitles", "types": ["movie", "series"], "idPrefixes": ["moviesdrive:", "tt"]},
        ],
        "types": ["movie", "series"],
        "catalogs": [
            {
                "type": "movie",
                "id": "moviesdrive_movies_latest",
                "name": "MoviesDrive - Phim Mới",
                "extra": [
                    {"name": "genre", "options": ["Tất cả"] + GENRE_OPTIONS, "isRequired": main_req},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "type": "movie",
                "id": "moviesdrive_movies_4k",
                "name": "MoviesDrive - Phim 4K UHD",
                "extra": [
                    {"name": "genre", "options": ["Tất cả"], "isRequired": True},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "type": "series",
                "id": "moviesdrive_series_latest",
                "name": "MoviesDrive - Phim Bộ (Series)",
                "extra": [
                    {"name": "genre", "options": ["Tất cả"] + GENRE_OPTIONS, "isRequired": main_req},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
        ],
    }


# ------------------------------------------------------------------
# Background workers (prewarm + cache autosave), started on first request
# ------------------------------------------------------------------
_BACKGROUND_STARTED = False


def start_background_tasks() -> None:
    global _BACKGROUND_STARTED
    if _BACKGROUND_STARTED:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _BACKGROUND_STARTED = True
    loop.create_task(perf.cache_autosave_loop())
    perf.schedule_prewarm(
        catalog.prewarm_jobs(), delay=1.0, label="MoviesDrive catalog prewarm"
    )
    logger.info("MoviesDrive background workers started (%s)", perf.cache_stats())


async def moviesdrive_startup() -> None:
    """Optional explicit hook for addon.py; the router also self-starts."""
    start_background_tasks()


async def moviesdrive_shutdown() -> None:
    perf.save_cache(force=True)
    await perf.aclose_client()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _proxy_url(base: str, direct_url: str, referer: Optional[str] = None) -> str:
    url = base + "/moviesdrive/stream_proxy?url=" + urllib.parse.quote(direct_url, safe="")
    if referer:
        url = url + "&referer=" + urllib.parse.quote(referer, safe="")
    return url


def _resolve_url(base: str, candidate: Dict[str, Any], mode: str = "direct") -> str:
    params: Dict[str, str] = {"ep": str(candidate.get("episode") or 1), "mode": mode}
    if candidate.get("archive_url"):
        params["arc"] = candidate["archive_url"]
    if candidate.get("hubcloud_url"):
        params["hc"] = candidate["hubcloud_url"]
    if candidate.get("post_url"):
        params["post"] = candidate["post_url"]
    return base + "/moviesdrive/resolve?" + urllib.parse.urlencode(params)


def _safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_. " else "_" for ch in (text or "video")).strip()


def _subtitle_url(base_url: str, clean_id: str, media_type: str, item_id: str, track: str) -> str:
    return (
        base_url
        + "/subtitles/vtt/"
        + clean_id
        + ".vtt?type="
        + media_type
        + "&orig_id="
        + urllib.parse.quote(item_id)
        + "&track="
        + track
    )


async def _warm_and_translate(
    media_type: str, item_id: str, candidates: List[Dict[str, Any]]
) -> None:
    """Resolve the best candidate in the background.

    This warms the /resolve cache so pressing Play is instant, and registers the
    real CDN URL - never the proxied one - for the subtitle pipeline, so ffprobe
    reads the file directly instead of looping back through our own proxy.
    Track 1 (Lingva) is generated right away; track 2 (Gemini -> Custom AI)
    starts on its own as soon as track 1 is done.
    """
    try:
        best = await warm_candidates(candidates)
        if not best or not best.get("url"):
            return
        direct_url = best["url"]
        try:
            from sync_vtt_service import STREAM_VIDEO_URL_CACHE, get_or_generate_fast_vtt
        except Exception as exc:
            logger.warning("Subtitle service unavailable: %s", exc)
            return
        STREAM_VIDEO_URL_CACHE[item_id] = direct_url
        await get_or_generate_fast_vtt(media_type, item_id, video_url=direct_url)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Pre-translation trigger error for %s: %s", item_id, exc)


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------
async def get_manifest():
    start_background_tasks()
    return JSONResponse(get_moviesdrive_manifest())


async def catalog_endpoint(
    request: Request,
    type: str,
    id: str,
    genre: Optional[str] = None,
    search: Optional[str] = None,
    skip: Optional[int] = 0,
):
    start_background_tasks()
    qp = request.query_params if request else {}
    final_genre = genre or qp.get("genre")
    final_search = search or qp.get("search")
    final_skip = skip if skip is not None else int(qp.get("skip", 0) if str(qp.get("skip", "")).isdigit() else 0)
    metas = await get_catalog_items(type, id, genre=final_genre, search=final_search, skip=final_skip or 0)
    return JSONResponse({"metas": metas})


async def catalog_extra_endpoint(request: Request, type: str, id: str, extra: str = ""):
    start_background_tasks()
    genre = None
    search = None
    skip = 0
    clean_extra = (extra or "").replace(".json", "")
    for pair in clean_extra.split("&"):
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        v = urllib.parse.unquote(v)
        if k == "genre":
            genre = v
        elif k == "search":
            search = v
        elif k == "skip":
            try:
                skip = int(v)
            except ValueError:
                pass
    if request:
        qp = request.query_params
        if not genre and "genre" in qp:
            genre = qp.get("genre")
        if not search and "search" in qp:
            search = qp.get("search")
        if skip == 0 and "skip" in qp and str(qp.get("skip")).isdigit():
            skip = int(qp.get("skip"))

    metas = await get_catalog_items(type, id, genre=genre, search=search, skip=skip)
    return JSONResponse({"metas": metas})


async def meta_endpoint(type: str, id: str):
    meta_obj = await get_meta_object(type, id)
    return JSONResponse({"meta": meta_obj})


async def stream_endpoint(request: Request, type: str, id: str):
    start_background_tasks()
    base = _base_url(request)

    post_url: Optional[str] = None
    display = ""
    season_num: Optional[int] = None
    episode_num: Optional[int] = None

    if id.startswith("moviesdrive:"):
        parts = id.split(":")
        slug = parts[1] if len(parts) > 1 else ""
        if not slug:
            return JSONResponse({"streams": []})
        season_num = int(parts[2]) if len(parts) > 2 else None
        episode_num = int(parts[3]) if len(parts) > 3 else (1 if type == "series" else None)
        post_url = current_base() + "/" + slug.strip("/") + "/"
        display = slug.replace("-", " ").strip()

    elif id.startswith("tt"):
        parts = id.split(":")
        imdb_id = parts[0]
        season_num = int(parts[1]) if len(parts) > 1 else None
        episode_num = int(parts[2]) if len(parts) > 2 else (1 if type == "series" else None)

        meta = await get_cinemeta_title(type, imdb_id)
        if not meta or not meta.get("name"):
            return JSONResponse({"streams": []})
        display = meta["name"]
        year = str(meta.get("year") or "")

        data = await search_moviesdrive_api(display, page=1)
        hits = data.get("hits", [])
        if not hits and year:
            data = await search_moviesdrive_api(display + " " + str(year), page=1)
            hits = data.get("hits", [])
        if not hits:
            return JSONResponse({"streams": []})

        # Match strictly with display and year, DO NOT pick an unrelated hit!
        def _norm_str(s: str) -> str:
            return re.sub(r"[^\w\s]", "", (s or "").lower()).strip()

        def _safe_year(val: Any) -> Optional[int]:
            if not val:
                return None
            m = re.search(r"\b(19\d\d|20\d\d)\b", str(val))
            if m:
                try:
                    return int(m.group(1))
                except Exception:
                    return None
            return None

        target_norm = _norm_str(display)
        target_words = [w for w in target_norm.split() if w not in ('a', 'an', 'the', 'and', 'or', 'of', 'in', 'to', 'for', 'with') and len(w) > 1]
        if not target_words:
            target_words = target_norm.split()

        target_year = _safe_year(year)

        valid_hits = []
        for hit in hits:
            doc = hit.get("document", {})
            p_title = _norm_str(doc.get("post_title", ""))
            p_slug = _norm_str(doc.get("permalink", "").replace("-", " "))
            
            # Check title match
            is_title_match = (target_norm in p_title or target_norm in p_slug or 
                              all(w in p_title or w in p_slug for w in target_words))
            if not is_title_match:
                continue

            p_year = _safe_year(doc.get("post_title", "") + " " + doc.get("permalink", ""))
            # For movies, year must match closely (+- 1 year)
            if type == "movie":
                if target_year and p_year and abs(target_year - p_year) > 1:
                    continue
            else:
                # For series, later seasons can be released years after series start year
                if target_year and p_year and p_year < (target_year - 1):
                    continue

            valid_hits.append(hit)

        matched_hit = None
        if type == "series" and season_num:
            s_num = int(season_num)
            # Prioritize post explicitly matching the requested season
            for hit in valid_hits:
                doc = hit.get("document", {})
                raw_text = (doc.get("post_title", "") + " " + doc.get("permalink", "")).lower()
                if (f"season {s_num}" in raw_text or 
                    f"season-{s_num}" in raw_text or 
                    f"s{s_num:02d}" in raw_text or
                    f"s{s_num}" in raw_text or 
                    re.search(rf"season\s*1\s*[-–]\s*(\d+)", raw_text)):
                    matched_hit = hit
                    break

        if not matched_hit and valid_hits:
            matched_hit = valid_hits[0]

        if not matched_hit:
            logger.info("No matching MoviesDrive post found for Cinemeta title '%s' (IMDb: %s)", display, imdb_id)
            return JSONResponse({"streams": []})

        permalink = matched_hit.get("document", {}).get("permalink", "")
        if not permalink:
            return JSONResponse({"streams": []})
        post_url = urllib.parse.urljoin(current_base() + "/", permalink)

    else:
        return JSONResponse({"streams": []})

    candidates = await collect_candidates(
        post_url, media_type=type, season_num=season_num, episode_num=episode_num
    )
    if not candidates:
        return JSONResponse({"streams": []})

    target_ep = candidates[0].get("episode") or 1
    safe_display = _safe_name(display) or "moviesdrive"
    if type == "series":
        filename = (
            safe_display
            + ".S"
            + str(season_num or 1).zfill(2)
            + "E"
            + str(target_ep).zfill(2)
            + ".mkv"
        )
    else:
        filename = safe_display + ".mkv"

    streams: List[Dict[str, Any]] = []
    for candidate in candidates:
        quality = candidate["quality"]
        label = candidate["label"] or display
        size = candidate.get("size") or ""

        if type == "series":
            title = display + " - Ep " + str(target_ep) + " [" + label + "]"
        else:
            title = display + " [" + label + "]"
        if size:
            title = title + "\n💾 " + str(size)

        hints = {"notWebReady": False, "filename": filename, "bingeGroup": "moviesdrive-" + quality}

        streams.append(
            {
                "name": "🎬 MoviesDrive [" + quality + "]",
                "title": title + "\n⚡ Direct CDN",
                "url": _resolve_url(base, candidate, mode="direct"),
                "behaviorHints": dict(hints),
            }
        )
        streams.append(
            {
                "name": "🎬 MoviesDrive Proxy [" + quality + "]",
                "title": title + "\n🛡️ Local Proxy Stream",
                "url": _resolve_url(base, candidate, mode="proxy"),
                "behaviorHints": dict(hints),
            }
        )

    asyncio.create_task(_warm_and_translate(type, id, candidates))
    return JSONResponse({"streams": streams})


async def moviesdrive_resolve(
    request: Request,
    arc: Optional[str] = None,
    hc: Optional[str] = None,
    post: Optional[str] = None,
    ep: int = 1,
    mode: str = "direct",
):
    """Resolve one stream on demand and redirect the player to it."""
    if not arc and not hc:
        raise HTTPException(status_code=400, detail="Missing arc or hc parameter")

    best = await resolve_playable_url(
        archive_url=arc, hubcloud_url=hc, post_url=post, episode=ep or 1
    )
    if not best or not best.get("url"):
        raise HTTPException(status_code=502, detail="Could not resolve a playable link")

    target = best["url"]
    if mode == "proxy":
        target = _proxy_url(_base_url(request), target, referer=GAMERXYT_REFERER)

    return RedirectResponse(
        target,
        status_code=302,
        headers={"Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"},
    )


async def moviesdrive_stream_proxy(request: Request, url: str, referer: Optional[str] = None):
    """Proxy a direct video stream, forwarding Range requests for instant seeking."""
    if not url:
        raise HTTPException(status_code=400, detail="Missing stream URL")
    clean_url = urllib.parse.unquote(url)

    req_headers = {"User-Agent": perf.USER_AGENT, "Accept": "*/*"}

    # Signed R2 / S3 / Google URLs reject a Referer header.
    if referer and not any(
        k in clean_url
        for k in ("cloudflarestorage.com", "r2.cloudflarestorage.com", "googleusercontent.com")
    ):
        req_headers["Referer"] = referer

    range_header = request.headers.get("range")
    if range_header:
        req_headers["range"] = range_header

    try:
        client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)
        upstream_req = client.build_request("GET", clean_url, headers=req_headers)
        upstream_resp = await client.send(upstream_req, stream=True)

        resp_headers = {}
        for key in ("content-range", "content-type", "accept-ranges", "content-length"):
            if key in upstream_resp.headers:
                resp_headers[key] = upstream_resp.headers[key]
        if "content-type" not in resp_headers:
            resp_headers["content-type"] = "video/x-matroska"
        resp_headers["accept-ranges"] = "bytes"
        resp_headers["Access-Control-Allow-Origin"] = "*"

        async def stream_generator():
            try:
                async for chunk in upstream_resp.aiter_bytes(chunk_size=128 * 1024):
                    yield chunk
            except Exception:
                pass
            finally:
                try:
                    await upstream_resp.aclose()
                except Exception:
                    pass
                try:
                    await client.aclose()
                except Exception:
                    pass

        return SafeStreamingResponse(
            stream_generator(),
            status_code=upstream_resp.status_code,
            headers=resp_headers,
        )
    except Exception as e:
        logger.error("Stream proxy exception for %s: %s", url, e)
        raise HTTPException(status_code=502, detail="Proxy error: " + str(e))


async def serve_synced_vtt(request: Request, item_id: str, type: str = "movie"):
    """Serve one of the two Vietnamese tracks, with HEAD support and a fallback cue.

    ?track=fast    (default) Lingva over the whole file, final on first answer.
    ?track=quality Gemini -> Custom AI, served progressively while it runs.
    """
    track = (request.query_params.get("track") or TRACK_FAST).lower()
    if track not in (TRACK_FAST, TRACK_QUALITY, "base", "raw", "original"):
        track = TRACK_FAST

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Content-Disposition": "inline",
        # The quality track keeps changing until it is done, so it must not be
        # cached by the player or the user would be stuck on an early version.
        "Cache-Control": (
            "public, max-age=86400"
            if track in (TRACK_FAST, "base", "raw", "original")
            else "no-store, no-cache, must-revalidate"
        ),
    }
    if request.method == "HEAD":
        return Response(status_code=200, media_type="text/vtt; charset=utf-8", headers=headers)

    raw_id = request.query_params.get("orig_id") or item_id
    target_id = raw_id[:-4] if raw_id.endswith((".srt", ".vtt")) else raw_id
    vtt_content = None
    try:
        from sync_vtt_service import get_track_vtt

        vtt_content = await get_track_vtt(type, target_id, track)
    except Exception as e:
        logger.warning("Error in serve_synced_vtt for %s (track=%s): %s", target_id, track, e)

    if not vtt_content or not vtt_content.strip():
        vtt_content = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:05.000\n[Đang tải phụ đề tiếng Việt...]"
        headers["Cache-Control"] = "no-store, no-cache, must-revalidate"

    vtt_text = vtt_content.strip()
    if not vtt_text.startswith("WEBVTT"):
        vtt_text = "WEBVTT\n\n" + vtt_text

    return Response(
        content=vtt_text.encode("utf-8"),
        media_type="text/vtt; charset=utf-8",
        headers=headers,
    )


async def serve_synced_srt(request: Request, item_id: str, type: str = "movie"):
    """Serve one of the tracks in standard .SRT format with attachment download headers."""
    track = (request.query_params.get("track") or "base").lower()
    raw_id = request.query_params.get("orig_id") or item_id
    target_id = raw_id[:-4] if raw_id.endswith((".srt", ".vtt")) else raw_id

    clean_name = item_id[:-4] if item_id.endswith((".srt", ".vtt")) else item_id
    filename = _safe_name(clean_name) + ("_vi" if track in (TRACK_FAST, TRACK_QUALITY) else "_eng") + ".srt"
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "public, max-age=86400",
    }
    if request.method == "HEAD":
        return Response(status_code=200, media_type="text/plain; charset=utf-8", headers=headers)

    srt_content = None
    try:
        from sync_vtt_service import get_track_srt
        srt_content = await get_track_srt(type, target_id, track)
    except Exception as e:
        logger.warning("Error in serve_synced_srt for %s (track=%s): %s", target_id, track, e)

    if not srt_content or not srt_content.strip():
        srt_content = "1\n00:00:01,000 --> 00:00:05,000\n[Đang tải phụ đề...]\n"

    return Response(
        content=srt_content.strip().encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers=headers,
    )


async def moviesdrive_subtitles(request: Request, type: str, id: str, extra: str = ""):
    """Serve subtitles: fast Lingva track, AI quality track, and base extracted track."""
    base_url = _base_url(request)
    clean_id = id.replace(":", "_").replace("/", "_")

    fast_url = _subtitle_url(base_url, clean_id, type, id, TRACK_FAST)
    quality_url = _subtitle_url(base_url, clean_id, type, id, TRACK_QUALITY)
    base_sub_url = _subtitle_url(base_url, clean_id, type, id, "base")
    base_srt_url = f"{base_url}/subtitles/srt/{clean_id}.srt?type={type}&orig_id={urllib.parse.quote(id)}&track=base"

    subtitles_list: List[Dict[str, Any]] = [
        {
            "id": "vi_fast_" + clean_id,
            "url": fast_url,
            "lang": "vie",
            "name": "🇻🇳 Tiếng Việt - Nhanh (Lingva, toàn bộ phim)",
        },
        {
            "id": "vi_quality_" + clean_id,
            "url": quality_url,
            "lang": "vie",
            "name": "🇻🇳 Tiếng Việt - AI chất lượng cao (Gemini, dịch ngầm)",
        },
        {
            "id": "vi_base_" + clean_id,
            "url": base_sub_url,
            "lang": "eng",
            "name": "📥 Phụ đề Gốc đã tách (Base / English)",
        },
    ]

    sep = "=" * 80
    logger.info(
        f"\n{sep}\n"
        f"🎯 [SUBTITLE DOWNLOAD LINKS] PHIM: {id}\n"
        f"   📥 LINK TẢI FILE .SRT GỐC (Trực tiếp):\n"
        f"      👉 {base_srt_url}\n"
        f"   🔗 Link tải Tiếng Việt Fast (.VTT):\n"
        f"      👉 {fast_url}\n"
        f"   🔗 Link tải Tiếng Việt AI Quality (.VTT):\n"
        f"      👉 {quality_url}\n"
        f"{sep}"
    )

    imdb_id = id
    if id.startswith("moviesdrive:"):
        resolved_imdb = await find_imdb_for_moviesdrive_id(type, id)
        if resolved_imdb:
            imdb_id = resolved_imdb

    if imdb_id and (imdb_id.startswith("tt") or ":" in imdb_id):
        subs = await fetch_opensubtitles(imdb_id, type, extra or "")
        subtitles_list.extend(subs)

    return JSONResponse(content={"subtitles": subtitles_list})


async def moviesdrive_cache_stats():
    return JSONResponse(perf.cache_stats())


# ------------------------------------------------------------------
# Route registration (every path is served with and without the prefix)
# ------------------------------------------------------------------
def _add(path: str, endpoint, methods: Optional[List[str]] = None) -> None:
    for full_path in (path, "/moviesdrive" + path):
        moviesdrive_router.add_api_route(full_path, endpoint, methods=methods or ["GET"])


_add("/manifest.json", get_manifest)
_add("/catalog/{type}/{id}.json", catalog_endpoint)
_add("/catalog/{type}/{id}/{extra}.json", catalog_extra_endpoint)
_add("/meta/{type}/{id}.json", meta_endpoint)
_add("/stream/{type}/{id}.json", stream_endpoint)
_add("/resolve", moviesdrive_resolve, ["GET", "HEAD"])
_add("/stream_proxy", moviesdrive_stream_proxy)
_add("/subtitles/vtt/{item_id}.vtt", serve_synced_vtt, ["GET", "HEAD"])
_add("/subtitles/srt/{item_id}.srt", serve_synced_srt, ["GET", "HEAD"])
_add("/subtitles/srt/{item_id}", serve_synced_srt, ["GET", "HEAD"])
_add("/subtitles/{type}/{id}.json", moviesdrive_subtitles)
_add("/subtitles/{type}/{id}/{extra}.json", moviesdrive_subtitles)
_add("/cache_stats", moviesdrive_cache_stats)


# ------------------------------------------------------------------
# Standalone Runner
# ------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="MoviesDrive Stremio Addon")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(moviesdrive_router)
    print("Starting MoviesDrive Stremio Addon at http://127.0.0.1:7004/moviesdrive/manifest.json")
    uvicorn.run(app, host="0.0.0.0", port=7004)
