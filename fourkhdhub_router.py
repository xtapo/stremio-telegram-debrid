"""
FastAPI router for 4KHDHub addon.
"""

import asyncio
import base64
import html as html_lib
import logging
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

from config import Config
import fourkhdhub_perf as perf
from fourkhdhub_perf import (
    CACHE,
    CACHE_TTL,
    STREAM_CACHE_TTL,
    get_cached,
    save_cache,
    set_cached,
)
import fourkhdhub_resolver as resolver
from fourkhdhub_resolver import (
    absolute,
    collect_candidates,
    current_base,
    parse_quality_badge,
    quality_rank,
    resolve_candidate,
    resolve_playable_url,
    strip_base,
    warm_candidates,
)
import fourkhdhub_catalog as catalog
from fourkhdhub_catalog import (
    CATEGORIES_MAP,
    CINEMETA_API,
    GENRE_OPTIONS,
    clean_title,
    find_fourkhdhub_for_imdb,
    get_catalog_items,
    get_meta_for_slug,
    search_fourkhdhub,
)

logger = logging.getLogger("fourkhdhub_addon")

fourkhdhub_router = APIRouter(prefix="", tags=["4khdhub"])

GAMERXYT_REFERER = "https://gamerxyt.com/"
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
# Manifest Definition
# ------------------------------------------------------------------
def get_fourkhdhub_manifest() -> Dict[str, Any]:
    show_on_board = getattr(Config, "ENABLE_BOARD_4KHDHUB", True)
    main_req = not show_on_board

    manifest: Dict[str, Any] = {
        "id": "com.stremio.4khdhub.addon",
        "version": "1.0.0",
        "name": "4KHDHub - 4K Ultra HD & Dolby Vision",
        "description": "Watch 4K UHD 2160p, Dolby Vision, HDR10+, 1080p HEVC Movies & TV Series from 4KHDHub with high-speed direct Cloudflare R2 & 10Gbps CDN streaming.",
        "resources": [
            "catalog",
            {"name": "meta", "types": ["movie", "series"], "idPrefixes": ["4khdhub:", "tt"]},
            {"name": "stream", "types": ["movie", "series"], "idPrefixes": ["4khdhub:", "tt"]},
        ] + ([{"name": "subtitles", "types": ["movie", "series"], "idPrefixes": ["4khdhub:", "tt"]}] if getattr(Config, "ENABLE_SUBTITLES", True) else []),
        "types": ["movie", "series"],
        "catalogs": [
            {
                "type": "movie",
                "id": "4khdhub_movies_latest",
                "name": "4KHDHub - Phim Mới Cập Nhật",
                "extra": [
                    {"name": "genre", "options": ["Tất cả"] + GENRE_OPTIONS, "isRequired": main_req},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "type": "movie",
                "id": "4khdhub_movies_4k_hdr",
                "name": "4KHDHub - 4K HDR & Dolby Vision",
                "extra": [
                    {"name": "genre", "options": ["Tất cả"], "isRequired": True},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "type": "movie",
                "id": "4khdhub_movies_english",
                "name": "4KHDHub - English Movies 4K",
                "extra": [
                    {"name": "genre", "options": ["Tất cả"], "isRequired": True},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "type": "series",
                "id": "4khdhub_series_latest",
                "name": "4KHDHub - Web Series & TV Shows 4K",
                "extra": [
                    {"name": "genre", "options": ["Tất cả", "Web Series", "English Series", "Hindi Series", "Korean Series", "Drama Series", "Netflix", "Anime"], "isRequired": main_req},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
        ],
    }
    return manifest


# ------------------------------------------------------------------
# URL Construction Helpers
# ------------------------------------------------------------------
def _base_url(request: Request) -> str:
    addon_url = getattr(Config, "ADDON_URL", None)
    if addon_url:
        return addon_url.rstrip("/")
    return str(request.base_url).rstrip("/")


def _proxy_url(base: str, target: str, referer: Optional[str] = None) -> str:
    encoded = urllib.parse.quote(target, safe="")
    url = f"{base}/4khdhub/stream_proxy?url={encoded}"
    if referer:
        url += f"&referer={urllib.parse.quote(referer, safe='')}"
    return url


def _playback_url(base: str, raw_url: str, post: str = "", ep: int = 1, mode: str = "direct") -> str:
    params = {"raw_url": raw_url, "mode": mode, "ep": str(ep)}
    if post:
        params["post"] = post
    return f"{base}/4khdhub/playback?{urllib.parse.urlencode(params)}"


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w\.\-\ ]", "", name).replace(" ", ".").strip(".")


# ------------------------------------------------------------------
# Background Tasks
# ------------------------------------------------------------------
_BG_STARTED = False


def start_background_tasks():
    global _BG_STARTED
    if _BG_STARTED:
        return
    _BG_STARTED = True

    async def _cache_saver():
        while True:
            await asyncio.sleep(perf.CACHE_SAVE_INTERVAL)
            try:
                save_cache()
            except Exception:
                pass

    try:
        asyncio.create_task(_cache_saver())
    except RuntimeError:
        pass


# ------------------------------------------------------------------
# Subtitles / AI Helpers
# ------------------------------------------------------------------
def _build_vtt_url(base: str, media_type: str, item_id: str, track: str = TRACK_FAST) -> str:
    clean_id = item_id.replace(":", "_")
    return (
        base
        + "/4khdhub/subtitles/vtt/"
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
    try:
        if not candidates:
            return
        direct_url = await resolve_candidate(candidates[0])
        if not direct_url:
            return
        try:
            from sync_vtt_service import STREAM_VIDEO_URL_CACHE, get_or_generate_fast_vtt
            STREAM_VIDEO_URL_CACHE[item_id] = direct_url
            await get_or_generate_fast_vtt(media_type, item_id, video_url=direct_url)
        except Exception as exc:
            logger.warning("4KHDHub subtitle service unavailable: %s", exc)
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


# ------------------------------------------------------------------
# Router Endpoint Functions
# ------------------------------------------------------------------
async def get_manifest():
    start_background_tasks()
    return JSONResponse(get_fourkhdhub_manifest())


async def catalog_endpoint(type: str, id: str):
    return await catalog_extra_endpoint(type, id, "")


async def catalog_extra_endpoint(type: str, id: str, extra: str = ""):
    start_background_tasks()
    genre = "Phim Mới"
    search = None
    skip = 0

    if id == "4khdhub_movies_4k_hdr":
        genre = "4K HDR"
    elif id == "4khdhub_movies_english":
        genre = "English Movies"
    elif id == "4khdhub_series_latest":
        genre = "Web Series"

    if extra:
        for pair in extra.split("&"):
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

    if search:
        metas = await search_fourkhdhub(search)
    else:
        metas = await get_catalog_items(category=genre, skip=skip)

    return JSONResponse({"metas": metas})


async def meta_endpoint(type: str, id: str):
    start_background_tasks()
    slug = id.replace("4khdhub:", "").split(":")[0]
    meta_obj = await get_meta_for_slug(slug, item_type=type)
    if not meta_obj:
        return JSONResponse({"meta": {}})
    return JSONResponse({"meta": meta_obj})


async def stream_endpoint(request: Request, type: str, id: str):
    start_background_tasks()
    base = _base_url(request)

    post_url: Optional[str] = None
    display = ""
    season_num: Optional[int] = None
    episode_num: Optional[int] = None

    if id.startswith("4khdhub:"):
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

        matched = await find_fourkhdhub_for_imdb(imdb_id, media_type=type)
        if not matched:
            return JSONResponse({"streams": []})

        post_url = matched[0].get("url")
        display = matched[0].get("name", "")

    else:
        return JSONResponse({"streams": []})

    if not post_url:
        return JSONResponse({"streams": []})

    candidates = await collect_candidates(
        post_url, media_type=type, season_num=season_num, episode_num=episode_num
    )
    if not candidates:
        return JSONResponse({"streams": []})

    target_ep = candidates[0].get("episode") or 1
    safe_display = _safe_name(display) or "4khdhub"
    if type == "series":
        filename = f"{safe_display}.S{str(season_num or 1).zfill(2)}E{str(target_ep).zfill(2)}.mkv"
    else:
        filename = f"{safe_display}.mkv"

    streams: List[Dict[str, Any]] = []
    for candidate in candidates:
        quality = candidate["quality"]
        label = candidate["label"] or display
        size = candidate.get("size") or ""

        if type == "series":
            title = f"{display} - Ep {target_ep} [{label}]"
        else:
            title = f"{display} [{label}]"
        if size:
            title = f"{title}\n📦 Size: {size}"

        hints = {"notWebReady": False, "filename": filename, "bingeGroup": f"4khdhub-{quality}"}

        streams.append({
            "name": f"⚡ [4KHDHub Direct] [{quality}]",
            "title": f"{title}\n🚀 Cloudflare R2 / 10Gbps CDN Fast Stream",
            "url": _playback_url(base, candidate["raw_url"], post=post_url, ep=target_ep, mode="direct"),
            "behaviorHints": dict(hints),
        })
        streams.append({
            "name": f"🛡️ [4KHDHub Proxy] [{quality}]",
            "title": f"{title}\n🔒 Local Stream Proxy",
            "url": _playback_url(base, candidate["raw_url"], post=post_url, ep=target_ep, mode="proxy"),
            "behaviorHints": dict(hints),
        })

    warm_candidates(candidates)
    asyncio.create_task(_warm_and_translate(type, id, candidates))
    return JSONResponse({"streams": streams})


async def fourkhdhub_resolve(
    request: Request,
    raw_url: str,
    mode: str = "direct",
    post: Optional[str] = None,
    ep: int = 1,
):
    if not raw_url:
        raise HTTPException(status_code=400, detail="Missing raw_url parameter")

    target = await resolve_candidate({"raw_url": raw_url, "post_url": post, "episode": ep})
    if not target:
        raise HTTPException(status_code=502, detail="Could not resolve a playable link from 4KHDHub")

    if mode == "proxy":
        target = _proxy_url(_base_url(request), target, referer=GAMERXYT_REFERER)

    return RedirectResponse(
        target,
        status_code=302,
        headers={"Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"},
    )


async def fourkhdhub_stream_proxy(
    request: Request,
    url: str = Query(..., description="Target CDN URL to proxy"),
    referer: Optional[str] = Query(None, description="Optional Referer header"),
):
    """Streams video with range request support."""
    if not url:
        raise HTTPException(status_code=400, detail="Missing url parameter")

    target_url = urllib.parse.unquote(url)
    req_headers = dict(perf.DEFAULT_HEADERS)
    if referer:
        req_headers["Referer"] = urllib.parse.unquote(referer)

    client = await perf.get_http_client()
    for header in ["range", "if-range"]:
        if header in request.headers:
            req_headers[header] = request.headers[header]

    try:
        backend_req = client.build_request("GET", target_url, headers=req_headers)
        backend_resp = await client.send(backend_req, stream=True)

        resp_headers = {}
        for h in [
            "content-range",
            "content-length",
            "accept-ranges",
            "content-type",
            "last-modified",
            "etag",
        ]:
            if h in backend_resp.headers:
                resp_headers[h] = backend_resp.headers[h]

        resp_headers["access-control-allow-origin"] = "*"

        async def stream_generator():
            try:
                async for chunk in backend_resp.aiter_bytes(chunk_size=65536):
                    yield chunk
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            finally:
                await backend_resp.aclose()

        return SafeStreamingResponse(
            stream_generator(),
            status_code=backend_resp.status_code,
            headers=resp_headers,
            media_type=backend_resp.headers.get("content-type", "video/mp4"),
        )
    except Exception as exc:
        logger.error("4KHDHub stream proxy failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Proxy failed: {exc}")


async def subtitles_endpoint(type: str, id: str):
    from config import Config
    if not getattr(Config, "ENABLE_SUBTITLES", True):
        return JSONResponse({"subtitles": []})

    base = getattr(Config, "ADDON_URL", "").rstrip("/")
    if not base:
        base = "http://localhost:7860"

    subtitles = [
        {
            "id": f"4khdhub_sub_fast_{id}",
            "url": _build_vtt_url(base, type, id, track=TRACK_FAST),
            "lang": "vie",
            "label": "🇻🇳 Tiếng Việt (AI Fast Progressive)",
        },
        {
            "id": f"4khdhub_sub_quality_{id}",
            "url": _build_vtt_url(base, type, id, track=TRACK_QUALITY),
            "lang": "vie",
            "label": "🇻🇳 Tiếng Việt (AI Quality Deep)",
        },
    ]
    return JSONResponse({"subtitles": subtitles})


# ------------------------------------------------------------------
# FastAPI Route Registration
# ------------------------------------------------------------------
fourkhdhub_router.add_api_route("/manifest.json", get_manifest, methods=["GET"])
fourkhdhub_router.add_api_route("/catalog/{type}/{id}.json", catalog_endpoint, methods=["GET"])
fourkhdhub_router.add_api_route("/catalog/{type}/{id}/{extra}.json", catalog_extra_endpoint, methods=["GET"])
fourkhdhub_router.add_api_route("/meta/{type}/{id}.json", meta_endpoint, methods=["GET"])
fourkhdhub_router.add_api_route("/stream/{type}/{id}.json", stream_endpoint, methods=["GET"])
fourkhdhub_router.add_api_route("/playback", fourkhdhub_resolve, methods=["GET"])
fourkhdhub_router.add_api_route("/stream_proxy", fourkhdhub_stream_proxy, methods=["GET"])
fourkhdhub_router.add_api_route("/subtitles/{type}/{id}.json", subtitles_endpoint, methods=["GET"])
