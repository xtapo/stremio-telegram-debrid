"""
FastAPI router for UHDMovies addon.
"""

import asyncio
import base64
import json
import logging
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

from config import Config
import uhdmovies_perf as perf
from uhdmovies_perf import (
    STREAM_CACHE_TTL,
    base_of,
    cached_call,
    get_active_base,
)
import uhdmovies_resolver as resolver
from uhdmovies_resolver import (
    absolute,
    current_base,
    resolve_candidate,
    strip_base,
)
import uhdmovies_catalog as catalog
from uhdmovies_catalog import (
    CATEGORIES_MAP,
    GENRE_OPTIONS,
    clean_title,
    find_uhdmovies_for_imdb,
    get_category_page,
    get_meta_for_slug,
    search_uhdmovies,
)

logger = logging.getLogger("uhdmovies_addon")

uhdmovies_router = APIRouter(prefix="", tags=["uhdmovies"])

TRACK_FAST = "fast"
TRACK_QUALITY = "quality"


class SafeStreamingResponse(StreamingResponse):
    async def __call__(self, scope, receive, send) -> None:
        async def safe_send(message):
            try:
                await send(message)
            except BaseException:
                return

        try:
            await super().__call__(scope, receive, safe_send)
        except BaseException:
            return


def _base_url(request: Request) -> str:
    addon_url = getattr(Config, "ADDON_URL", None)
    if addon_url:
        return addon_url.rstrip("/")
    return str(request.base_url).rstrip("/")


def _proxy_url(base: str, target: str, referer: Optional[str] = None) -> str:
    encoded = urllib.parse.quote(target, safe="")
    url = f"{base}/uhdmovies/stream_proxy?url={encoded}"
    if referer:
        url += f"&referer={urllib.parse.quote(referer, safe='')}"
    return url


def _playback_url(base: str, raw_url: str, post: str = "", ep: int = 1, mode: str = "direct") -> str:
    params = {"raw_url": raw_url, "mode": mode, "ep": str(ep)}
    if post:
        params["post"] = post
    return f"{base}/uhdmovies/playback?{urllib.parse.urlencode(params)}"


# ------------------------------------------------------------------
# Manifest Definition
# ------------------------------------------------------------------
def get_uhdmovies_manifest() -> Dict[str, Any]:
    show_on_board = getattr(Config, "ENABLE_BOARD_UHDMOVIES", True)

    manifest: Dict[str, Any] = {
        "id": "com.stremio.uhdmovies.addon",
        "version": "1.0.0",
        "name": "UHDMovies - 4K Ultra HD & 1080p HEVC",
        "description": "Watch 4K UHD 2160p, 4K HDR/Dolby Vision, 1080p 10Bit HEVC & 60FPS Movies & Series from UHDMovies with high-speed direct CDN streaming.",
        "resources": [
            "catalog",
            {"name": "meta", "types": ["movie", "series"], "idPrefixes": ["uhdmovies:", "tt"]},
            {"name": "stream", "types": ["movie", "series"], "idPrefixes": ["uhdmovies:", "tt"]},
        ] + ([{"name": "subtitles", "types": ["movie", "series"], "idPrefixes": ["uhdmovies:", "tt"]}] if getattr(Config, "ENABLE_SUBTITLES", True) else []),
        "types": ["movie", "series"],
        "catalogs": [
            {
                "type": "movie",
                "id": "uhdmovies_movies_latest",
                "name": "UHDMovies - Phim Mới Cập Nhật",
                "pageSize": catalog.STREMIO_PAGE_SIZE,
                "extra": [
                    {"name": "genre", "options": ["Tất cả"] + [g for g in GENRE_OPTIONS if g != "Tất cả"], "isRequired": False},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "type": "movie",
                "id": "uhdmovies_movies_4k_hdr",
                "name": "UHDMovies - 4K HDR & Dolby Vision",
                "pageSize": catalog.STREMIO_PAGE_SIZE,
                "extra": [{"name": "skip", "isRequired": False}],
            },
            {
                "type": "movie",
                "id": "uhdmovies_movies_2160p_hevc",
                "name": "UHDMovies - 2160p 4K HEVC",
                "pageSize": catalog.STREMIO_PAGE_SIZE,
                "extra": [{"name": "skip", "isRequired": False}],
            },
            {
                "type": "movie",
                "id": "uhdmovies_movies_1080p_10bit",
                "name": "UHDMovies - 1080p 10Bit HEVC",
                "pageSize": catalog.STREMIO_PAGE_SIZE,
                "extra": [{"name": "skip", "isRequired": False}],
            },
            {
                "type": "series",
                "id": "uhdmovies_series_latest",
                "name": "UHDMovies - TV & Web Series",
                "pageSize": catalog.STREMIO_PAGE_SIZE,
                "extra": [
                    {"name": "genre", "options": ["Tất cả", "TV Series", "Web Series"], "isRequired": False},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
        ],
        "idPrefixes": ["uhdmovies:", "tt"],
        "behaviorHints": {
            "configurable": False,
            "configurationRequired": False,
        },
    }

    if not show_on_board:
        for cat in manifest.get("catalogs", []):
            cat["extraRequired"] = ["search"]
            cat.pop("pageSize", None)

    return manifest


async def get_manifest():
    return JSONResponse(get_uhdmovies_manifest(), headers={"Access-Control-Allow-Origin": "*"})


# ------------------------------------------------------------------
# Catalog Endpoints
# ------------------------------------------------------------------
async def catalog_endpoint(
    request: Request,
    type: str,
    id: str,
    search: Optional[str] = None,
    genre: Optional[str] = None,
    skip: Optional[int] = None,
):
    return await catalog_extra_endpoint(
        request=request,
        type=type,
        id=id,
        extra="",
        search=search,
        genre=genre,
        skip=skip,
    )


async def catalog_extra_endpoint(
    request: Request,
    type: str,
    id: str,
    extra: str = "",
    search: Optional[str] = None,
    genre: Optional[str] = None,
    skip: Optional[int] = None,
):
    if not getattr(Config, "ENABLE_SOURCE_UHDMOVIES", True):
        return JSONResponse({"metas": []}, headers={"Access-Control-Allow-Origin": "*"})

    search_query = search or request.query_params.get("search")
    genre_query = genre or request.query_params.get("genre")
    skip_val = skip if skip is not None else int(request.query_params.get("skip", 0) or 0)

    clean_extra = extra.replace(".json", "") if extra else ""
    if clean_extra:
        for part in clean_extra.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                v = urllib.parse.unquote(v)
                if k == "search":
                    search_query = v
                elif k == "genre":
                    genre_query = v
                elif k == "skip":
                    try:
                        skip_val = int(v)
                    except ValueError:
                        pass

    if genre_query == "Tất cả":
        genre_query = None

    clean_id = id.replace(".json", "")
    items = await catalog.get_catalog_items(
        cat_type=type,
        cat_id=clean_id,
        genre=genre_query,
        search=search_query,
        skip=skip_val,
    )

    metas = []
    for item in items:
        metas.append({
            "id": item["id"],
            "type": item["type"],
            "name": item["name"],
            "poster": item.get("poster", ""),
            "year": item.get("year"),
            "description": f"{item['raw_title']}",
        })

    return JSONResponse({"metas": metas}, headers={"Access-Control-Allow-Origin": "*"})



# ------------------------------------------------------------------
# Meta Endpoints
# ------------------------------------------------------------------
async def meta_endpoint(type: str, id: str):
    logger.info("meta_endpoint called with type=%s, id=%s", type, id)
    if not getattr(Config, "ENABLE_SOURCE_UHDMOVIES", True):
        return JSONResponse({"meta": {}}, headers={"Access-Control-Allow-Origin": "*"})

    clean_id = id[:-5] if id.endswith(".json") else id

    if clean_id.startswith("uhdmovies:"):
        slug = clean_id.split("uhdmovies:", 1)[1]
        slug = slug[:-5] if slug.endswith(".json") else slug
        logger.info("meta_endpoint resolving slug: %s", slug)
        meta = await get_meta_for_slug(slug, item_type=type)
        logger.info("meta_endpoint got meta: %s", bool(meta))
        if meta:
            return JSONResponse({"meta": meta}, headers={"Access-Control-Allow-Origin": "*"})
        return JSONResponse({"meta": {}}, headers={"Access-Control-Allow-Origin": "*"})

    if clean_id.startswith("tt"):
        # Cinemeta fallback
        imdb_id = clean_id.split(":")[0]
        meta = await catalog.get_cinemeta_meta(type, imdb_id)
        if meta:
            return JSONResponse({"meta": meta}, headers={"Access-Control-Allow-Origin": "*"})

    return JSONResponse({"meta": {}}, headers={"Access-Control-Allow-Origin": "*"})


# ------------------------------------------------------------------
# Stream Endpoints
# ------------------------------------------------------------------
async def stream_endpoint(request: Request, type: str, id: str):
    if not getattr(Config, "ENABLE_SOURCE_UHDMOVIES", True):
        return JSONResponse({"streams": []}, headers={"Access-Control-Allow-Origin": "*"})

    clean_id = id[:-5] if id.endswith(".json") else id
    target_episode: Optional[int] = None
    target_season: Optional[int] = None

    candidates: List[Dict[str, Any]] = []

    if clean_id.startswith("uhdmovies:"):
        parts = clean_id.split(":")
        slug = parts[1]
        slug = slug[:-5] if slug.endswith(".json") else slug
        post_url = absolute(slug)
        if len(parts) >= 4:
            try:
                target_season = int(parts[2])
                target_episode = int(parts[3])
            except ValueError:
                pass
        if post_url:
            candidates = await resolver.collect_candidates(post_url, episode=target_episode)
    elif clean_id.startswith("tt"):
        parts = clean_id.split(":")
        imdb_id = parts[0]
        imdb_id = imdb_id[:-5] if imdb_id.endswith(".json") else imdb_id
        if len(parts) >= 3:
            try:
                target_season = int(parts[1])
                target_episode = int(parts[2])
            except ValueError:
                pass

        matched_items = await find_uhdmovies_for_imdb(
            imdb_id, is_series=(type == "series" or target_episode is not None)
        )
        for item in matched_items[:3]:
            u = item.get("url")
            if u:
                item_cands = await resolver.collect_candidates(u, episode=target_episode)
                if item_cands:
                    candidates.extend(item_cands)
                    if len(candidates) >= resolver.MAX_CANDIDATES:
                        break

    if not candidates:
        return JSONResponse({"streams": []}, headers={"Access-Control-Allow-Origin": "*"})

    base = _base_url(request)
    streams = []

    for c in candidates:
        raw_url = c["raw_url"]
        badge = c.get("badge") or "HD"
        size = c.get("size") or ""
        ep = c.get("episode")
        desc = c.get("title") or ""

        title_lines = [f"⚡ UHDMovies | {badge}"]
        details = []
        if size:
            details.append(f"📦 {size}")
        if ep:
            details.append(f"📺 Ep {ep}")
        if "dual audio" in desc.lower() or "hindi" in desc.lower():
            details.append("🌐 Dual Audio")
        if "atmos" in desc.lower():
            details.append("🔊 Atmos")

        if details:
            title_lines.append(" • ".join(details))

        candidate_post = c.get("post_url", "")
        playback_url = _playback_url(
            base, raw_url, post=candidate_post, ep=ep or 1, mode="direct"
        )

        streams.append({
            "name": f"UHDMovies\n{badge}",
            "title": "\n".join(title_lines),
            "url": playback_url,
            "behaviorHints": {
                "notWebReady": False,
                "bingeGroup": f"uhdmovies-{badge}",
            },
        })

    # Prewarm the top candidates in background
    for c in candidates[:resolver.WARM_CANDIDATES]:
        asyncio.create_task(resolve_candidate(c))

    return JSONResponse({"streams": streams}, headers={"Access-Control-Allow-Origin": "*"})


# ------------------------------------------------------------------
# Playback & Stream Proxy
# ------------------------------------------------------------------
async def uhdmovies_playback(
    request: Request,
    raw_url: str = Query(...),
    mode: str = "direct",
    post: Optional[str] = None,
    ep: int = 1,
):
    if not raw_url:
        raise HTTPException(status_code=400, detail="Missing raw_url parameter")

    target = await resolve_candidate({"raw_url": raw_url, "post_url": post, "episode": ep})
    if not target:
        raise HTTPException(status_code=502, detail="Could not resolve a playable link from UHDMovies")

    if mode == "proxy":
        target = _proxy_url(_base_url(request), target)

    return RedirectResponse(
        target,
        status_code=302,
        headers={"Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"},
    )


async def uhdmovies_stream_proxy(request: Request, url: str, referer: Optional[str] = None):
    if not url:
        raise HTTPException(status_code=400, detail="Missing stream URL")
    clean_url = urllib.parse.unquote(url)

    req_headers = {"User-Agent": perf.USER_AGENT, "Accept": "*/*"}
    if referer and not any(
        k in clean_url for k in ("googleusercontent.com", "r2.dev", "cloudflarestorage.com", "workers.dev", "driveseed.org")
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
        logger.error("UHDMovies stream proxy error for %s: %s", url, e)
        raise HTTPException(status_code=502, detail=f"Proxy error: {e}")


# ------------------------------------------------------------------
# Subtitles Endpoint
# ------------------------------------------------------------------
def _subtitle_url(base: str, clean_id: str, type: str, full_id: str, track: str) -> str:
    params = {
        "from": "uhdmovies",
        "id": clean_id,
        "type": type,
        "full_id": full_id,
        "track": track,
    }
    return f"{base}/subtitles/vtt?{urllib.parse.urlencode(params)}"


async def uhdmovies_subtitles(request: Request, type: str, id: str, extra: str = ""):
    if not getattr(Config, "ENABLE_SUBTITLES", True):
        return JSONResponse({"subtitles": []}, headers={"Access-Control-Allow-Origin": "*"})

    subtitles = []
    clean_id = id.replace(".json", "")
    base = _base_url(request)

    if getattr(Config, "AUTO_VIET_SUB", True):
        subtitles = [
            {
                "id": f"uhdmovies-fast-{clean_id}",
                "url": _subtitle_url(base, clean_id, type, id, TRACK_FAST),
                "lang": "vie",
                "name": "🇻🇳 Tiếng Việt - Nhanh (Lingva, toàn bộ phim)",
            },
            {
                "id": f"uhdmovies-quality-{clean_id}",
                "url": _subtitle_url(base, clean_id, type, id, TRACK_QUALITY),
                "lang": "vie",
                "name": "🇻🇳 Tiếng Việt - AI chất lượng cao (Gemini, dịch ngầm)",
            },
        ]
    return JSONResponse({"subtitles": subtitles}, headers={"Access-Control-Allow-Origin": "*"})


# ------------------------------------------------------------------
# Route Registration
# ------------------------------------------------------------------
def _add(path: str, endpoint, methods: Optional[List[str]] = None) -> None:
    uhdmovies_router.add_api_route(path, endpoint, methods=methods or ["GET"])
    if path.endswith(".json"):
        uhdmovies_router.add_api_route(path[:-5], endpoint, methods=methods or ["GET"])


_add("/manifest.json", get_manifest)
_add("/catalog/{type}/{id}.json", catalog_endpoint)
_add("/catalog/{type}/{id}/{extra}.json", catalog_extra_endpoint)
_add("/meta/{type}/{id}.json", meta_endpoint)
_add("/stream/{type}/{id}.json", stream_endpoint)
_add("/playback", uhdmovies_playback, ["GET", "HEAD"])
_add("/stream_proxy", uhdmovies_stream_proxy)
_add("/subtitles/{type}/{id}.json", uhdmovies_subtitles)
_add("/subtitles/{type}/{id}/{extra}.json", uhdmovies_subtitles)
