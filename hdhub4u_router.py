"""
FastAPI router for HDHub4u addon.
"""

import asyncio
import html as html_lib
import logging
import urllib.parse
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse

import hdhub4u_perf as perf
from hdhub4u_perf import (
    CACHE,
    CACHE_TTL,
    STREAM_CACHE_TTL,
    get_cached,
    save_cache,
    set_cached,
)
import hdhub4u_resolver as resolver
from hdhub4u_resolver import (
    collect_candidates,
    current_base,
    parse_quality_badge,
    quality_rank,
    resolve_candidate,
    resolve_playable_url,
    warm_candidates,
)
import hdhub4u_catalog as catalog
from hdhub4u_catalog import (
    CATEGORIES_MAP,
    CINEMETA_API,
    GENRE_OPTIONS,
    find_hdhub4u_for_imdb,
    get_catalog_items,
    get_cinemeta_title,
    get_meta_object,
    search_hdhub4u,
)

logger = logging.getLogger("hdhub4u_addon")

hdhub4u_router = APIRouter(prefix="", tags=["hdhub4u"])

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
def get_hdhub4u_manifest() -> Dict[str, Any]:
    from config import Config
    show_on_board = getattr(Config, "ENABLE_BOARD_HDHUB4U", True)
    main_req = not show_on_board

    return {
        "id": "com.stremio.hdhub4u.addon",
        "version": "1.0.0",
        "name": "HDHub4u - 4K Movies & Series",
        "description": "Watch Hollywood, Bollywood, Dual Audio 4K UHD, 1080p, 720p Movies & TV Series from HDHub4u with high-speed direct CDN streaming.",
        "resources": [
            "catalog",
            {"name": "meta", "types": ["movie", "series"], "idPrefixes": ["hdhub4u:", "tt"]},
            {"name": "stream", "types": ["movie", "series"], "idPrefixes": ["hdhub4u:", "tt"]},
        ] + ([{"name": "subtitles", "types": ["movie", "series"], "idPrefixes": ["hdhub4u:", "tt"]}] if getattr(Config, "ENABLE_SUBTITLES", True) else []),
        "types": ["movie", "series"],
        "catalogs": [
            {
                "type": "movie",
                "id": "hdhub4u_movies_latest",
                "name": "HDHub4u - Phim Mới Cập Nhật",
                "extra": [
                    {"name": "genre", "options": ["Tất cả"] + GENRE_OPTIONS, "isRequired": main_req},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "type": "movie",
                "id": "hdhub4u_movies_hollywood",
                "name": "HDHub4u - Hollywood Movies",
                "extra": [
                    {"name": "genre", "options": ["Tất cả"], "isRequired": True},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "type": "movie",
                "id": "hdhub4u_movies_bollywood",
                "name": "HDHub4u - Bollywood Movies",
                "extra": [
                    {"name": "genre", "options": ["Tất cả"], "isRequired": True},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "type": "series",
                "id": "hdhub4u_series_latest",
                "name": "HDHub4u - Phim Bộ (Web Series)",
                "extra": [
                    {"name": "genre", "options": ["Tất cả"], "isRequired": main_req},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
        ],
    }


# ------------------------------------------------------------------
# Background Tasks
# ------------------------------------------------------------------
_BACKGROUND_STARTED = False


def start_background_tasks() -> None:
    global _BACKGROUND_STARTED
    if _BACKGROUND_STARTED:
        return
    _BACKGROUND_STARTED = True
    try:
        asyncio.create_task(perf.resolve_dynamic_host())
    except RuntimeError:
        pass


async def hdhub4u_startup() -> None:
    start_background_tasks()


async def hdhub4u_shutdown() -> None:
    perf.save_cache_sync()
    await perf.close_client()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _base_url(request: Request) -> str:
    from config import Config
    if getattr(Config, "ADDON_URL", None) and not Config.ADDON_URL.startswith("http://localhost"):
        return Config.ADDON_URL.rstrip("/")
    return str(request.base_url).rstrip("/")


def _proxy_url(base: str, direct_url: str, referer: Optional[str] = None) -> str:
    url = base + "/hdhub4u/stream_proxy?url=" + urllib.parse.quote(direct_url, safe="")
    if referer:
        url = url + "&referer=" + urllib.parse.quote(referer, safe="")
    return url


def _resolve_url(base: str, candidate: Dict[str, Any], mode: str = "direct") -> str:
    params: Dict[str, str] = {
        "raw_url": candidate.get("raw_url", ""),
        "mode": mode,
        "post": candidate.get("post_url", ""),
    }
    return base + "/hdhub4u/resolve?" + urllib.parse.urlencode(params)


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
            logger.warning("HDHub4u subtitle service unavailable: %s", exc)
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


# ------------------------------------------------------------------
# Router Endpoint Functions
# ------------------------------------------------------------------
async def get_manifest():
    start_background_tasks()
    return JSONResponse(get_hdhub4u_manifest())


manifest_endpoint = get_manifest


async def catalog_endpoint(type: str, id: str):
    return await catalog_extra_endpoint(type, id, "")


async def catalog_extra_endpoint(type: str, id: str, extra: str = ""):
    start_background_tasks()
    genre = "Phim Mới"
    search = None
    skip = 0

    if id == "hdhub4u_movies_hollywood":
        genre = "Hollywood"
    elif id == "hdhub4u_movies_bollywood":
        genre = "Bollywood"
    elif id == "hdhub4u_series_latest":
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
        metas = await search_hdhub4u(search)
    else:
        metas = await get_catalog_items(category=genre, skip=skip)

    return JSONResponse({"metas": metas})


async def meta_endpoint(type: str, id: str):
    start_background_tasks()
    slug = id.replace("hdhub4u:", "").split(":")[0]
    meta_obj = await get_meta_object(slug)
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

    if id.startswith("hdhub4u:"):
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

        matched = await find_hdhub4u_for_imdb(imdb_id, media_type=type)
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
    safe_display = _safe_name(display) or "hdhub4u"
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

        hints = {"notWebReady": False, "filename": filename, "bingeGroup": f"hdhub4u-{quality}"}

        streams.append({
            "name": f"⚡ [HDHub4u Direct] [{quality}]",
            "title": f"{title}\n🚀 Cloudflare R2 / 10Gbps CDN Fast Stream",
            "url": _resolve_url(base, candidate, mode="direct"),
            "behaviorHints": dict(hints),
        })
        streams.append({
            "name": f"🛡️ [HDHub4u Proxy] [{quality}]",
            "title": f"{title}\n🔒 Local Stream Proxy",
            "url": _resolve_url(base, candidate, mode="proxy"),
            "behaviorHints": dict(hints),
        })

    warm_candidates(candidates)
    asyncio.create_task(_warm_and_translate(type, id, candidates))
    return JSONResponse({"streams": streams})


async def hdhub4u_resolve(
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
        raise HTTPException(status_code=502, detail="Could not resolve a playable link from HDHub4u")

    if mode == "proxy":
        target = _proxy_url(_base_url(request), target, referer=GAMERXYT_REFERER)

    return RedirectResponse(
        target,
        status_code=302,
        headers={"Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"},
    )


async def hdhub4u_stream_proxy(request: Request, url: str, referer: Optional[str] = None):
    if not url:
        raise HTTPException(status_code=400, detail="Missing stream URL")
    clean_url = urllib.parse.unquote(url)

    req_headers = {"User-Agent": perf.USER_AGENT, "Accept": "*/*"}
    if referer and not any(
        k in clean_url
        for k in ("cloudflarestorage.com", "r2.cloudflarestorage.com", "r2.dev", "googleusercontent.com")
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
        logger.error("HDHub4u stream proxy exception for %s: %s", url, e)
        raise HTTPException(status_code=502, detail=f"Proxy error: {e}")


async def hdhub4u_subtitles(request: Request, type: str, id: str, extra: str = ""):
    from config import Config
    if not getattr(Config, "ENABLE_SUBTITLES", True):
        return JSONResponse({"subtitles": []})
    subtitles = []
    if getattr(Config, "AUTO_VIET_SUB", True):
        subtitles = [
            {
                "id": f"hdhub4u-fast-{clean_id}",
                "url": _subtitle_url(base, clean_id, type, id, TRACK_FAST),
                "lang": "vie",
                "name": "🇻🇳 Tiếng Việt - Nhanh (Lingva, toàn bộ phim)",
            },
            {
                "id": f"hdhub4u-quality-{clean_id}",
                "url": _subtitle_url(base, clean_id, type, id, TRACK_QUALITY),
                "lang": "vie",
                "name": "🇻🇳 Tiếng Việt - AI chất lượng cao (Gemini, dịch ngầm)",
            },
        ]
    return JSONResponse({"subtitles": subtitles})


# ------------------------------------------------------------------
# Route Registration
# ------------------------------------------------------------------
def _add(path: str, endpoint, methods: Optional[List[str]] = None) -> None:
    for full_path in (path, "/hdhub4u" + path):
        hdhub4u_router.add_api_route(full_path, endpoint, methods=methods or ["GET"])


_add("/manifest.json", get_manifest)
_add("/catalog/{type}/{id}.json", catalog_endpoint)
_add("/catalog/{type}/{id}/{extra}.json", catalog_extra_endpoint)
_add("/meta/{type}/{id}.json", meta_endpoint)
_add("/stream/{type}/{id}.json", stream_endpoint)
_add("/resolve", hdhub4u_resolve, ["GET", "HEAD"])
_add("/stream_proxy", hdhub4u_stream_proxy)
_add("/subtitles/{type}/{id}.json", hdhub4u_subtitles)
_add("/subtitles/{type}/{id}/{extra}.json", hdhub4u_subtitles)


if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="HDHub4u Stremio Addon")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(hdhub4u_router)
    print("Starting HDHub4u Stremio Addon at http://127.0.0.1:7005/hdhub4u/manifest.json")
    uvicorn.run(app, host="0.0.0.0", port=7005)
