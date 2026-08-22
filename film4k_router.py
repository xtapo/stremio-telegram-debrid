import asyncio
import json
import logging
import re
import shutil
import subprocess
import time
import unicodedata
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

from config import Config

logger = logging.getLogger(__name__)

film4k_router = APIRouter(prefix="", tags=["film4k"])

# ------------------------------------------------------------------
# Cache & Memory Management
# ------------------------------------------------------------------
_film4k_cache: Dict[str, Tuple[Any, float]] = {}
_channels_by_id: Dict[str, Dict[str, Any]] = {}
CHANNELS_CACHE_TTL = 3600   # 1 hour
EVENTS_CACHE_TTL = 180      # 3 minutes
STREAM_CACHE_TTL = 1800     # 30 minutes for signed stream URLs

_film4k_client: Optional[httpx.AsyncClient] = None
_client_loop: Optional[asyncio.AbstractEventLoop] = None


def get_film4k_cookie() -> str:
    """Retrieve the current Film4k session cookie from Config or env."""
    cookie = getattr(Config, "FILM4K_COOKIE", "")
    if not cookie:
        cookie = (
            "session=eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImphbWlkMjA0QGdtYWlsLmNvbSIsIm5hbWUiOiJUaGkgVHJhbiIs"
            "ImltYWdlIjoiaHR0cHM6Ly9saDMuZ29vZ2xldXNlcmNvbnRlbnQuY29tL2EvQUNnOG9jSV9HWURzQ3JHaFV4WUN1NVRk"
            "NWxka3laRHUxcm5TSUJQVGU0dkJKZUFaalhWYW95aUc9czk2LWMiLCJzdWIiOiI2YTg4NDYyOGQ5MmQwNmI3OTRjNjQ2NzUi"
            "LCJpYXQiOjE3ODczMTU3NTIsImV4cCI6MTc4OTkwNzc1Mn0.nNwoSi3H9HwNkYCYVTj4PhS0IVKoAdus4racY3pOMBo"
        )
    return cookie.strip()


def get_film4k_base_url() -> str:
    return getattr(Config, "FILM4K_BASE_URL", "https://film4k.net").rstrip("/")


def get_film4k_client() -> httpx.AsyncClient:
    global _film4k_client, _client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if (
        _film4k_client is None
        or _film4k_client.is_closed
        or _client_loop != current_loop
        or (current_loop and current_loop.is_closed())
    ):
        _client_loop = current_loop
        _film4k_client = httpx.AsyncClient(
            timeout=httpx.Timeout(5.0, connect=2.5),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=30, max_connections=60),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": f"{get_film4k_base_url()}/tv",
                "Origin": get_film4k_base_url(),
            },
        )
    return _film4k_client


# ------------------------------------------------------------------
# Channel Categorization & Genre Filters
# ------------------------------------------------------------------
GENRE_OPTIONS = [
    "Tất cả",
    "K+ Truyền Hình",
    "VTV",
    "HTV / HTVC",
    "Thể Thao",
    "Phim & Điện Ảnh",
    "Thiếu Nhi & Hoạt Hình",
    "Khoa Học & Khám Phá",
    "Tin Tức & Thời Sự",
    "Âm Nhạc & Giải Trí",
    "VTC",
    "Đài Địa Phương",
    "Kênh Quốc Tế & Tổng Hợp",
]


def normalize_text(text: str) -> str:
    """Normalize text for insensitive searching and diacritic removal."""
    if not text:
        return ""
    text = text.lower().strip()
    nfkd = unicodedata.normalize("NFD", text)
    stripped = "".join([c for c in nfkd if unicodedata.category(c) != "Mn"])
    return re.sub(r"[^a-z0-9]", "", stripped)


def categorize_channel(ch: Dict[str, Any]) -> str:
    name = (ch.get("name") or "").lower()
    ch_id = (ch.get("id") or "").lower()

    if any(k in name or k in ch_id for k in ["k+", "k-plus", "k plus"]):
        return "K+ Truyền Hình"
    if any(k in name or k in ch_id for k in ["vtv"]):
        return "VTV"
    if any(k in name or k in ch_id for k in ["htv", "htvc", "thuần việt", "phim hd"]):
        return "HTV / HTVC"
    if any(k in name or k in ch_id for k in ["vtc"]):
        return "VTC"
    if any(
        k in name or k in ch_id
        for k in [
            "sport", "thể thao", "football", "golf", "tennis", "nba", "uefa",
            "fifa", "fpt sport", "on sport", "red bull", "wwe"
        ]
    ):
        return "Thể Thao"
    if any(
        k in name or k in ch_id
        for k in [
            "hbo", "cinemax", "cinema", "phim", "movie", "hollywood", "action",
            "box", "warner", "axn", "galaxy", "kix", "dramas", "paramount"
        ]
    ):
        return "Phim & Điện Ảnh"
    if any(
        k in name or k in ch_id
        for k in [
            "cartoon", "disney", "anime", "kid", "thiếu nhi", "hoạt hình",
            "bibi", "dreamworks", "nick", "baby"
        ]
    ):
        return "Thiếu Nhi & Hoạt Hình"
    if any(
        k in name or k in ch_id
        for k in [
            "discovery", "nat geo", "national geographic", "animal", "khám phá",
            "history", "travel", "planet", "tlc", "food", "da vinci", "outdoor"
        ]
    ):
        return "Khoa Học & Khám Phá"
    if any(
        k in name or k in ch_id
        for k in [
            "cnn", "bbc", "news", "tin tức", "thời sự", "bloomberg", "nhk", "dw",
            "france 24", "cna", "tv5", "al jazeera", "arirang", "truyền hình quốc hội"
        ]
    ):
        return "Tin Tức & Thời Sự"
    if any(
        k in name or k in ch_id
        for k in ["music", "âm nhạc", "mnet", "mtv", "itv", "ca nhạc", "yan", "zing"]
    ):
        return "Âm Nhạc & Giải Trí"
    if any(
        k in name or k in ch_id
        for k in [
            "hà nội", "hanoitv", "thvl", "vĩnh long", "đà nẵng", "hải phòng",
            "cần thơ", "bình dương", "đồng nai", "quảng ninh", "huế", "ninh bình",
            "bình định", "thái nguyên", "khánh hòa", "tây ninh", "long an",
            "tiền giang", "bến tre", "an giang", "kiên giang", "cà mau",
            "bạc liêu", "sóc trăng", "trà vinh", "hậu giang", "vũng tàu",
            "lâm đồng", "đắk lắk", "gia lai", "kon tum", "đắk nông",
            "bình phước", "bình thuận", "ninh thuận", "phú yên", "quảng ngãi",
            "quảng nam", "quảng trị", "quảng bình", "hà tĩnh", "nghệ an",
            "thanh hóa", "nam định", "thái bình", "hải dương", "hưng yên",
            "bắc ninh", "bắc giang", "vĩnh phúc", "phú thọ", "hà giang",
            "tuyên quang", "cao bằng", "bắc kạn", "lạng sơn", "lào cai",
            "yên bái", "điện biên", "lai châu", "sơn la", "hòa bình"
        ]
    ):
        return "Đài Địa Phương"
    return "Kênh Quốc Tế & Tổng Hợp"


def _load_local_fallback_channels() -> List[Dict[str, Any]]:
    """Load bundled local channels database for instant 0ms startup."""
    import os
    candidates = [
        os.path.join(os.path.dirname(__file__), "scratch", "film4k_channels.json"),
        os.path.join(os.path.dirname(__file__), "film4k_channels.json"),
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    raw = json.load(f).get("channels", [])
                    for ch in raw:
                        ch["category"] = categorize_channel(ch)
                        if ch.get("id"):
                            _channels_by_id[ch["id"]] = ch
                    return raw
            except Exception as e:
                logger.warning(f"Failed loading local fallback channels from {p}: {e}")
    return []


# ------------------------------------------------------------------
# Film4k API Fetchers
# ------------------------------------------------------------------
async def fetch_film4k_channels() -> List[Dict[str, Any]]:
    """Fetch and cache list of 200+ TV channels from Film4k with instant local fallback."""
    global _channels_by_id
    now = time.time()
    if "channels" in _film4k_cache:
        data, exp = _film4k_cache["channels"]
        if now < exp:
            return data

    base_url = get_film4k_base_url()
    cookie = get_film4k_cookie()
    client = get_film4k_client()

    headers = {"Cookie": cookie}
    try:
        r = await client.get(f"{base_url}/api/tv/channels", headers=headers)
        if r.status_code == 200:
            data = r.json().get("channels", [])
            for ch in data:
                ch["category"] = categorize_channel(ch)
                if ch.get("id"):
                    _channels_by_id[ch["id"]] = ch
            _film4k_cache["channels"] = (data, now + CHANNELS_CACHE_TTL)
            return data
        else:
            logger.warning(f"Film4k channels API returned status {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"Error fetching Film4k channels (using local/stale cache): {e}")

    # Fallback to in-memory stale cache or local file
    if "channels" in _film4k_cache:
        return _film4k_cache["channels"][0]

    local_data = _load_local_fallback_channels()
    if local_data:
        _film4k_cache["channels"] = (local_data, now + CHANNELS_CACHE_TTL)
        return local_data

    return []


async def fetch_film4k_events() -> List[Dict[str, Any]]:
    """Fetch and cache list of live sports / streaming events from Film4k."""
    now = time.time()
    if "events" in _film4k_cache:
        data, exp = _film4k_cache["events"]
        if now < exp:
            return data

    base_url = get_film4k_base_url()
    cookie = get_film4k_cookie()
    client = get_film4k_client()

    headers = {"Cookie": cookie}
    try:
        r = await client.get(f"{base_url}/api/tv/events", headers=headers)
        if r.status_code == 200:
            data = r.json().get("events", [])
            _film4k_cache["events"] = (data, now + EVENTS_CACHE_TTL)
            return data
        else:
            logger.warning(f"Film4k events API returned status {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"Error fetching Film4k events: {e}")

    if "events" in _film4k_cache:
        return _film4k_cache["events"][0]
    return []


async def resolve_film4k_stream(item_id: str) -> Optional[Dict[str, Any]]:
    """Resolve live HLS stream URL for a TV channel or event ID."""
    clean_id = item_id.replace("film4k:channel:", "").replace("film4k:event:", "").replace("film4k:", "")
    cache_key = f"stream:{clean_id}"
    now = time.time()

    if cache_key in _film4k_cache:
        data, exp = _film4k_cache[cache_key]
        if now < exp:
            return data

    base_url = get_film4k_base_url()
    cookie = get_film4k_cookie()
    client = get_film4k_client()

    headers = {"Cookie": cookie}
    try:
        r = await client.get(f"{base_url}/api/tv/{urllib.parse.quote(clean_id)}/stream", headers=headers)
        if r.status_code == 200:
            data = r.json()
            if data and data.get("url"):
                _film4k_cache[cache_key] = (data, now + STREAM_CACHE_TTL)
                return data
            logger.warning(f"Film4k stream response missing URL for {clean_id}: {data}")
        elif r.status_code == 401:
            logger.error(f"Film4k authorization failed (401). Please update FILM4K_COOKIE.")
        else:
            logger.warning(f"Film4k stream API returned {r.status_code} for {clean_id}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"Error resolving Film4k stream for {clean_id}: {e}")

    return None


# ------------------------------------------------------------------
# Stremio Manifest
# ------------------------------------------------------------------
def get_film4k_manifest(api_key: str = "") -> Dict[str, Any]:
    show_on_board = getattr(Config, "ENABLE_BOARD_FILM4K_TV", True)
    main_req = not show_on_board

    return {
        "id": "com.stremio.film4k.tv",
        "version": "1.0.0",
        "name": "Film4k - Kênh Truyền Hình & Trực Tiếp TV",
        "description": "Xem 200+ kênh truyền hình Việt Nam, K+, Thể Thao, Quốc Tế & Sự Kiện Thể Thao Trực Tiếp Full HD từ Film4k.net",
        "logo": "https://film4k.net/favicon-32.png",
        "resources": [
            "catalog",
            {
                "name": "meta",
                "types": ["tv"],
                "idPrefixes": ["film4k:"]
            },
            {
                "name": "stream",
                "types": ["tv"],
                "idPrefixes": ["film4k:"]
            }
        ],
        "types": ["tv"],
        "catalogs": [
            {
                "type": "tv",
                "id": "film4k_tv_channels",
                "name": "Film4k - Kênh Truyền Hình (Live TV)",
                "extra": [
                    {"name": "genre", "options": GENRE_OPTIONS, "isRequired": main_req},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False}
                ]
            },
            {
                "type": "tv",
                "id": "film4k_tv_events",
                "name": "Film4k - Sự Kiện & Thể Thao Trực Tiếp",
                "extra": [
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False}
                ]
            }
        ],
        "behaviorHints": {
            "configurable": False,
            "configurationRequired": False
        }
    }


# ------------------------------------------------------------------
# Manifest Endpoints
# ------------------------------------------------------------------
@film4k_router.get("/manifest.json")
@film4k_router.get("/film4k/manifest.json")
@film4k_router.get("/{api_key}/film4k/manifest.json")
async def manifest_endpoint(api_key: str = ""):
    if not getattr(Config, "ENABLE_SOURCE_FILM4K_TV", True):
        raise HTTPException(status_code=404, detail="Film4k Live TV is disabled")
    return JSONResponse(get_film4k_manifest(api_key))


# ------------------------------------------------------------------
# Catalog Endpoints
# ------------------------------------------------------------------
@film4k_router.get("/catalog/{type}/{id}.json")
@film4k_router.get("/catalog/{type}/{id}/{extra}.json")
@film4k_router.get("/film4k/catalog/{type}/{id}.json")
@film4k_router.get("/film4k/catalog/{type}/{id}/{extra}.json")
@film4k_router.get("/{api_key}/film4k/catalog/{type}/{id}.json")
@film4k_router.get("/{api_key}/film4k/catalog/{type}/{id}/{extra}.json")
async def catalog_endpoint(
    type: str,
    id: str,
    extra: Optional[str] = None,
    api_key: str = ""
):
    if not getattr(Config, "ENABLE_SOURCE_FILM4K_TV", True):
        return JSONResponse({"metas": []})

    # Parse extra params
    genre_filter = None
    search_query = None
    skip_val = 0

    if extra:
        pairs = extra.split("&")
        for p in pairs:
            if "=" in p:
                k, v = p.split("=", 1)
                v = urllib.parse.unquote(v).strip()
                if k == "genre":
                    genre_filter = v
                elif k == "search":
                    search_query = v
                elif k == "skip":
                    try:
                        skip_val = int(v)
                    except ValueError:
                        skip_val = 0

    metas = []

    # 1. Live Events Catalog
    if id == "film4k_tv_events":
        events = await fetch_film4k_events()
        for ev in events:
            ev_id = ev.get("id", "")
            title = ev.get("title") or "Sự kiện trực tiếp"
            image = ev.get("image") or "https://film4k.net/favicon-32.png"
            status = ev.get("status") or "live"
            
            # Search filter
            if search_query:
                norm_q = normalize_text(search_query)
                norm_title = normalize_text(title)
                if norm_q not in norm_title:
                    continue

            status_badge = "🔴 LIVE NOW" if status == "live" else ("⏳ Sắp diễn ra" if status == "upcoming" else "⏹️ Đã kết thúc")
            desc = f"{status_badge}\nSự kiện thể thao & trực tiếp từ Film4k."
            if ev.get("begin"):
                try:
                    import datetime
                    t_str = datetime.datetime.fromtimestamp(ev["begin"]).strftime("%H:%M %d/%m/%Y")
                    desc += f"\nBắt đầu: {t_str}"
                except Exception:
                    pass

            metas.append({
                "id": f"film4k:event:{ev_id}",
                "type": "tv",
                "name": f"[{status.upper()}] {title}",
                "poster": image,
                "background": image,
                "logo": image,
                "description": desc,
                "genres": ["Thể Thao", "Trực Tiếp", "Sự Kiện"],
                "posterShape": "landscape",
            })

    # 2. TV Channels Catalog
    else:
        channels = await fetch_film4k_channels()
        for ch in channels:
            ch_id = ch.get("id", "")
            name = ch.get("name") or ch_id
            logo = ch.get("logo") or "https://film4k.net/favicon-32.png"
            category = ch.get("category") or "Kênh Khác"
            number = ch.get("number")

            # Genre filter
            if genre_filter and genre_filter != "Tất cả":
                if genre_filter != category:
                    continue

            # Search filter
            if search_query:
                norm_q = normalize_text(search_query)
                norm_name = normalize_text(name)
                norm_id = normalize_text(ch_id)
                if norm_q not in norm_name and norm_q not in norm_id:
                    continue

            number_prefix = f"#{number} " if number else ""
            desc = f"Kênh {name} ({category})\nNguồn phát: Film4k.net HLS Full HD / HD"

            metas.append({
                "id": f"film4k:channel:{ch_id}",
                "type": "tv",
                "name": f"{number_prefix}{name}",
                "poster": logo,
                "background": logo,
                "logo": logo,
                "description": desc,
                "genres": [category, "Truyền Hình"],
                "posterShape": "square",
            })

    # Apply pagination skip
    if skip_val > 0 and skip_val < len(metas):
        metas = metas[skip_val:]

    return JSONResponse({"metas": metas})


# ------------------------------------------------------------------
# Meta Endpoints
# ------------------------------------------------------------------
@film4k_router.get("/meta/{type}/{id}.json")
@film4k_router.get("/film4k/meta/{type}/{id}.json")
@film4k_router.get("/{api_key}/film4k/meta/{type}/{id}.json")
async def meta_endpoint(type: str, id: str, api_key: str = ""):
    if not getattr(Config, "ENABLE_SOURCE_FILM4K_TV", True):
        raise HTTPException(status_code=404, detail="Film4k Live TV is disabled")

    is_event = "event:" in id
    clean_id = id.replace("film4k:channel:", "").replace("film4k:event:", "").replace("film4k:", "")

    if is_event:
        events = await fetch_film4k_events()
        found = next((e for e in events if e.get("id") == clean_id), None)
        if not found:
            # Generate generic meta
            return JSONResponse({
                "meta": {
                    "id": id,
                    "type": "tv",
                    "name": f"Sự kiện {clean_id}",
                    "poster": "https://film4k.net/favicon-32.png",
                    "description": "Sự kiện trực tiếp Film4k",
                    "genres": ["Thể Thao", "Trực Tiếp"]
                }
            })
        
        title = found.get("title") or clean_id
        image = found.get("image") or "https://film4k.net/favicon-32.png"
        status = found.get("status") or "live"
        return JSONResponse({
            "meta": {
                "id": id,
                "type": "tv",
                "name": title,
                "poster": image,
                "background": image,
                "logo": image,
                "description": f"🔴 Sự kiện trực tiếp: {title}\nTrạng thái: {status.upper()}",
                "genres": ["Thể Thao", "Trực Tiếp"],
                "posterShape": "landscape"
            }
        })
    else:
        channels = await fetch_film4k_channels()
        found = next((c for c in channels if c.get("id") == clean_id), None)
        name = found.get("name") if found else clean_id
        logo = found.get("logo") if found else "https://film4k.net/favicon-32.png"
        category = found.get("category") if found else "Kênh Truyền Hình"
        number = found.get("number") if found else ""

        return JSONResponse({
            "meta": {
                "id": id,
                "type": "tv",
                "name": name,
                "poster": logo,
                "background": logo,
                "logo": logo,
                "description": f"Kênh truyền hình {name} (#{number})\nThể loại: {category}\nNguồn phát trực tiếp tốc độ cao Film4k",
                "genres": [category, "Truyền Hình"],
                "posterShape": "square"
            }
        })


# ------------------------------------------------------------------
# Stream Endpoints (Stremio & Direct)
# ------------------------------------------------------------------
@film4k_router.get("/stream/{type}/{id}.json")
@film4k_router.get("/film4k/stream/{type}/{id}.json")
@film4k_router.get("/{api_key}/film4k/stream/{type}/{id}.json")
async def stream_endpoint(request: Request, type: str, id: str, api_key: str = ""):
    if not getattr(Config, "ENABLE_SOURCE_FILM4K_TV", True):
        return JSONResponse({"streams": []})

    clean_id = id.replace("film4k:channel:", "").replace("film4k:event:", "").replace("film4k:", "")
    stream_data = await resolve_film4k_stream(clean_id)

    if not stream_data or not stream_data.get("url") or not str(stream_data["url"]).startswith("http"):
        return JSONResponse({"streams": []})

    stream_url = stream_data["url"]
    
    # Check if channel name is known
    ch = _channels_by_id.get(clean_id)
    ch_name = ch.get("name") if ch else clean_id

    clear_key = stream_data.get("clearKey")
    clear_keys = stream_data.get("clearKeys")

    # Format standard clearKeys dict { "<keyId>": "<key>" }
    formatted_clearkeys = {}
    if clear_key and isinstance(clear_key, dict) and clear_key.get("keyId") and clear_key.get("key"):
        formatted_clearkeys[clear_key["keyId"]] = clear_key["key"]
    elif clear_keys and isinstance(clear_keys, dict):
        formatted_clearkeys = clear_keys

    streams: List[Dict[str, Any]] = []

    # 1. If channel has DRM ClearKey, add Server-Side Auto-Decrypted Stream first (Fix Green Screen on Stremio Desktop / MPV!)
    if formatted_clearkeys:
        scheme = request.url.scheme
        host = request.headers.get("host") or f"127.0.0.1:{Config.PORT}"
        base_addon = f"{scheme}://{host}"
        key_part = f"/{api_key}" if api_key else ""
        decrypt_url = f"{base_addon}{key_part}/film4k/decrypt/{clean_id}.ts"

        streams.append({
            "name": "Film4k Live [Auto-Decrypted]",
            "title": f"🔓 {ch_name}\n[Đã tự động giải mã DRM • Fix màn hình xanh • Full HD]",
            "url": decrypt_url,
            "behaviorHints": {
                "notWebReady": False
            }
        })

    # 2. Direct CDN Stream
    direct_stream: Dict[str, Any] = {
        "name": "Film4k Live [Direct CDN]",
        "title": f"📺 {ch_name}\n[Luồng trực tiếp CDN • Tốc độ cao]",
        "url": stream_url,
        "behaviorHints": {
            "notWebReady": False,
            "proxyHeaders": {
                "request": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Referer": "https://film4k.net/tv"
                }
            }
        }
    }

    if formatted_clearkeys:
        direct_stream["behaviorHints"]["clearKeys"] = formatted_clearkeys
        if clear_key:
            direct_stream["behaviorHints"]["clearKey"] = clear_key

    streams.append(direct_stream)
    return JSONResponse({"streams": streams})


# ------------------------------------------------------------------
# Live On-The-Fly DRM Decryption Stream Endpoint (/film4k/decrypt/{id}.ts)
# ------------------------------------------------------------------
@film4k_router.get("/decrypt/{id}")
@film4k_router.get("/decrypt/{id}.ts")
@film4k_router.get("/film4k/decrypt/{id}")
@film4k_router.get("/film4k/decrypt/{id}.ts")
@film4k_router.get("/{api_key}/film4k/decrypt/{id}")
@film4k_router.get("/{api_key}/film4k/decrypt/{id}.ts")
async def decrypt_stream_endpoint(request: Request, id: str, api_key: str = ""):
    """Stream live decrypted video using ffmpeg on-the-fly (Fixes Green Screen in Stremio)."""
    clean_id = id.replace(".ts", "").replace("film4k:channel:", "").replace("film4k:event:", "").replace("film4k:", "")
    stream_data = await resolve_film4k_stream(clean_id)
    if not stream_data or not stream_data.get("url"):
        raise HTTPException(status_code=404, detail="Stream not found")

    url = stream_data["url"]
    clear_key = stream_data.get("clearKey") or {}
    key_hex = clear_key.get("key")
    if not key_hex and stream_data.get("clearKeys") and isinstance(stream_data["clearKeys"], dict):
        key_hex = list(stream_data["clearKeys"].values())[0]

    # If no encryption key found, redirect directly to original stream
    if not key_hex:
        return RedirectResponse(url=url, status_code=302)

    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
    cmd = [
        ffmpeg_bin,
        "-nostdin",
        "-hide_banner",
        "-loglevel", "error",
        "-cenc_decryption_key", key_hex,
        "-i", url,
        "-c", "copy",
        "-f", "mpegts",
        "pipe:1"
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=65536
        )
    except Exception as e:
        logger.error(f"Failed to start ffmpeg decryption process: {e}")
        return RedirectResponse(url=url, status_code=302)

    async def stream_generator():
        loop = asyncio.get_running_loop()
        try:
            while True:
                chunk = await loop.run_in_executor(None, proc.stdout.read, 65536)
                if not chunk:
                    break
                yield chunk
        except (asyncio.CancelledError, GeneratorExit, Exception):
            pass
        finally:
            try:
                proc.terminate()
                proc.kill()
            except Exception:
                pass

    return StreamingResponse(
        stream_generator(),
        media_type="video/mp2t",
        headers={
            "Content-Type": "video/mp2t",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Accept-Ranges": "none",
            "Connection": "close"
        }
    )


# ------------------------------------------------------------------
# Dynamic Live Stream Redirector (/film4k/live/{id}.m3u8)
# ------------------------------------------------------------------
@film4k_router.get("/live/{id}.m3u8")
@film4k_router.get("/film4k/live/{id}.m3u8")
@film4k_router.get("/{api_key}/film4k/live/{id}.m3u8")
async def live_stream_redirect(id: str, api_key: str = ""):
    """Redirect to the freshest signed HLS stream on the fly."""
    clean_id = id.replace(".m3u8", "").replace("film4k:channel:", "").replace("film4k:event:", "").replace("film4k:", "")
    stream_data = await resolve_film4k_stream(clean_id)

    if not stream_data or not stream_data.get("url"):
        raise HTTPException(status_code=404, detail="Stream not found or expired token")

    return RedirectResponse(url=stream_data["url"], status_code=302)


# ------------------------------------------------------------------
# IPTV M3U Playlist Endpoint (/film4k/playlist.m3u)
# ------------------------------------------------------------------
@film4k_router.get("/playlist.m3u")
@film4k_router.get("/channels.m3u")
@film4k_router.get("/film4k/playlist.m3u")
@film4k_router.get("/film4k/channels.m3u")
@film4k_router.get("/{api_key}/film4k/playlist.m3u")
@film4k_router.get("/{api_key}/film4k/channels.m3u")
async def m3u_playlist_endpoint(request: Request, api_key: str = ""):
    """Generate standard M3U IPTV playlist for TiviMate, VLC, OTT Navigator, Kodi, etc."""
    if not getattr(Config, "ENABLE_SOURCE_FILM4K_TV", True):
        raise HTTPException(status_code=404, detail="Film4k Live TV is disabled")

    # Base host for stream redirect links
    base_addon = getattr(Config, "ADDON_URL", "").rstrip("/")
    if not base_addon or base_addon.startswith("http://localhost"):
        # Use Host header from incoming request
        scheme = request.url.scheme
        host = request.headers.get("host") or f"127.0.0.1:{Config.PORT}"
        base_addon = f"{scheme}://{host}"

    key_part = f"/{api_key}" if api_key else ""
    
    channels = await fetch_film4k_channels()
    events = await fetch_film4k_events()

    lines = [
        "#EXTM3U x-tvg-url=\"\"",
        "#PLAYLIST:Film4k Live TV & Sports (200+ Channels)",
    ]

    # Add Live Events
    for ev in events:
        ev_id = ev.get("id", "")
        title = ev.get("title") or "Sự kiện trực tiếp"
        logo = ev.get("image") or ""
        status = (ev.get("status") or "live").upper()
        stream_link = f"{base_addon}{key_part}/film4k/live/{ev_id}.m3u8"

        lines.append(
            f'#EXTINF:-1 tvg-id="{ev_id}" tvg-name="{title}" tvg-logo="{logo}" group-title="⚽ Sự Kiện Trực Tiếp",[{status}] {title}'
        )
        lines.append(stream_link)

    # Add Channels
    for ch in channels:
        ch_id = ch.get("id", "")
        name = ch.get("name") or ch_id
        logo = ch.get("logo") or ""
        number = ch.get("number") or ""
        category = ch.get("category") or "Kênh Khác"
        stream_link = f"{base_addon}{key_part}/film4k/live/{ch_id}.m3u8"

        lines.append(
            f'#EXTINF:-1 tvg-id="{ch_id}" tvg-name="{name}" tvg-logo="{logo}" tvg-chno="{number}" group-title="{category}",{name}'
        )
        lines.append(stream_link)

    m3u_content = "\n".join(lines)
    return Response(
        content=m3u_content,
        media_type="application/vnd.apple.mpegurl",
        headers={
            "Content-Disposition": 'inline; filename="film4k_tv.m3u"',
            "Access-Control-Allow-Origin": "*",
        }
    )


# ------------------------------------------------------------------
# Cookie Update & Status API
# ------------------------------------------------------------------
@film4k_router.get("/status")
@film4k_router.get("/film4k/status")
async def film4k_status():
    channels = await fetch_film4k_channels()
    events = await fetch_film4k_events()
    cookie = get_film4k_cookie()
    
    return JSONResponse({
        "status": "online" if len(channels) > 0 else "offline",
        "channels_count": len(channels),
        "events_count": len(events),
        "cookie_configured": bool(cookie),
        "cookie_preview": cookie[:30] + "..." if cookie else "None",
        "cache_entries": len(_film4k_cache)
    })


# ------------------------------------------------------------------
# Web TV Player UI (/film4k/tv or /film4k/player)
# ------------------------------------------------------------------
@film4k_router.get("/tv", response_class=HTMLResponse)
@film4k_router.get("/player", response_class=HTMLResponse)
@film4k_router.get("/film4k/tv", response_class=HTMLResponse)
@film4k_router.get("/film4k/player", response_class=HTMLResponse)
async def web_tv_player():
    """Ultra-modern Web Live TV Player with HLS.js, Channel Switcher, and Search."""
    channels = await fetch_film4k_channels()
    events = await fetch_film4k_events()
    
    channels_json = json.dumps(channels, ensure_ascii=False)
    events_json = json.dumps(events, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Film4k Live TV - Xem 200+ Kênh Truyền Hình & Thể Thao</title>
  <link rel="icon" href="https://film4k.net/favicon-32.png">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/shaka-player/4.7.11/shaka-player.compiled.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
  <style>
    :root {{
      --bg: #07080c;
      --card-bg: #0e111a;
      --card-hover: #171c2a;
      --primary: #3b82f6;
      --primary-glow: rgba(59, 130, 246, 0.5);
      --accent: #10b981;
      --danger: #ef4444;
      --text: #f3f4f6;
      --text-dim: #9ca3af;
      --border: rgba(255, 255, 255, 0.08);
      --radius: 12px;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: 'Plus Jakarta Sans', sans-serif; }}
    html, body {{ height: 100%; width: 100%; overflow: hidden; background: var(--bg); color: var(--text); }}
    
    /* Header */
    header {{
      height: 60px;
      background: rgba(14, 17, 26, 0.95);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
      padding: 0 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      z-index: 100;
    }}
    .brand {{ display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 1.2rem; color: #fff; text-decoration: none; }}
    .brand img {{ width: 28px; height: 28px; border-radius: 6px; }}
    .badge-live {{ background: #ef4444; color: #fff; font-size: 0.68rem; font-weight: 800; padding: 2px 7px; border-radius: 20px; letter-spacing: 0.5px; animation: pulse 2s infinite; }}
    @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}

    /* Layout */
    .main-layout {{ display: grid; grid-template-columns: 1fr 400px; height: calc(100vh - 60px); width: 100%; overflow: hidden; }}
    
    /* Player Section */
    .player-section {{ display: flex; flex-direction: column; height: 100%; background: #000; position: relative; overflow: hidden; }}
    .video-wrapper {{ flex: 1; min-height: 0; position: relative; display: flex; align-items: center; justify-content: center; background: #000; overflow: hidden; }}
    video {{ width: 100%; height: 100%; object-fit: contain; background: #000; }}
    
    /* Channel Info Overlay & Unmute Banner */
    .top-left-overlay {{
      position: absolute; top: 16px; left: 16px; display: flex; align-items: center; gap: 10px;
      background: rgba(10, 12, 18, 0.75); backdrop-filter: blur(10px); padding: 8px 16px; border-radius: 30px; border: 1px solid var(--border);
      z-index: 20; transition: opacity 0.3s;
    }}
    .unmute-btn {{
      position: absolute; top: 16px; right: 16px; display: flex; align-items: center; gap: 8px;
      background: rgba(239, 68, 68, 0.9); color: #fff; font-weight: 700; font-size: 0.85rem; padding: 8px 16px; border-radius: 30px;
      border: 1px solid rgba(255,255,255,0.2); cursor: pointer; z-index: 20; box-shadow: 0 4px 15px rgba(239, 68, 68, 0.4);
      animation: bounce 1.5s infinite alternate;
    }}
    @keyframes bounce {{ from {{ transform: scale(1); }} to {{ transform: scale(1.05); }} }}

    /* Loading & Error States */
    .player-state-overlay {{
      position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center;
      background: rgba(7, 8, 12, 0.88); backdrop-filter: blur(6px); z-index: 15; text-align: center; padding: 20px;
    }}
    .spinner {{ width: 44px; height: 44px; border: 3px solid rgba(255,255,255,0.1); border-top-color: var(--primary); border-radius: 50%; animation: spin 0.8s linear infinite; margin-bottom: 16px; }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}

    /* Bottom Info Bar */
    .channel-info-bar {{
      height: 64px; flex-shrink: 0; background: var(--card-bg); border-top: 1px solid var(--border);
      padding: 0 20px; display: flex; justify-content: space-between; align-items: center; z-index: 20;
    }}
    .channel-title {{ font-size: 1.05rem; font-weight: 700; color: #fff; }}
    .channel-meta {{ font-size: 0.8rem; color: var(--text-dim); margin-top: 2px; }}

    /* Sidebar */
    .sidebar {{ background: var(--card-bg); border-left: 1px solid var(--border); display: flex; flex-direction: column; height: 100%; overflow: hidden; }}
    .sidebar-controls {{ padding: 12px 16px; border-bottom: 1px solid var(--border); display: flex; flex-direction: column; gap: 8px; flex-shrink: 0; }}
    .search-box {{
      width: 100%; background: #07080d; border: 1px solid var(--border); border-radius: 8px;
      padding: 9px 14px; color: #fff; font-size: 0.88rem; outline: none; transition: border-color 0.2s;
    }}
    .search-box:focus {{ border-color: var(--primary); }}
    
    .genre-scroll {{ display: flex; gap: 6px; overflow-x: auto; padding-bottom: 4px; scrollbar-width: none; }}
    .genre-scroll::-webkit-scrollbar {{ display: none; }}
    .genre-pill {{
      padding: 5px 12px; border-radius: 20px; background: rgba(255, 255, 255, 0.04); font-size: 0.72rem;
      font-weight: 600; color: var(--text-dim); cursor: pointer; white-space: nowrap; border: 1px solid transparent; transition: all 0.2s;
    }}
    .genre-pill:hover, .genre-pill.active {{ background: var(--primary); color: #fff; border-color: var(--primary-glow); }}

    .channel-list {{ flex: 1; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 4px; }}
    .channel-item {{
      display: flex; align-items: center; gap: 12px; padding: 9px 12px; background: rgba(255, 255, 255, 0.02);
      border-radius: var(--radius); border: 1px solid transparent; cursor: pointer; transition: all 0.15s;
    }}
    .channel-item:hover {{ background: var(--card-hover); transform: translateY(-1px); }}
    .channel-item.active {{ background: rgba(59, 130, 246, 0.15); border-color: var(--primary); }}
    .channel-logo {{ width: 40px; height: 40px; border-radius: 8px; object-fit: contain; background: #000; padding: 3px; flex-shrink: 0; }}
    .channel-fallback {{ width: 40px; height: 40px; border-radius: 8px; background: #1e2230; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.75rem; color: #94a3b8; flex-shrink: 0; }}
    .channel-details {{ flex: 1; min-width: 0; }}
    .channel-name {{ font-size: 0.88rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .channel-cat {{ font-size: 0.72rem; color: var(--text-dim); margin-top: 2px; }}

    /* Equalizer animation for playing channel */
    .playing-eq {{ display: flex; align-items: flex-end; gap: 2px; height: 14px; width: 14px; margin-left: 6px; }}
    .playing-eq span {{ width: 3px; background: var(--primary); border-radius: 2px; animation: eq 1s ease-in-out infinite alternate; }}
    .playing-eq span:nth-child(1) {{ height: 60%; animation-delay: 0.2s; }}
    .playing-eq span:nth-child(2) {{ height: 100%; animation-delay: 0.4s; }}
    .playing-eq span:nth-child(3) {{ height: 40%; animation-delay: 0.1s; }}
    @keyframes eq {{ 0% {{ height: 20%; }} 100% {{ height: 100%; }} }}

    .btn {{
      padding: 6px 14px; border-radius: 8px; font-weight: 600; font-size: 0.78rem; text-decoration: none;
      display: inline-flex; align-items: center; gap: 6px; cursor: pointer; border: none; transition: 0.2s;
    }}
    .btn-primary {{ background: var(--primary); color: #fff; }}
    .btn-primary:hover {{ filter: brightness(1.1); }}
    .btn-outline {{ background: rgba(255,255,255,0.04); border: 1px solid var(--border); color: var(--text); }}
    .btn-outline:hover {{ background: rgba(255,255,255,0.09); border-color: rgba(255,255,255,0.2); }}

    @media (max-width: 900px) {{
      .main-layout {{ grid-template-columns: 1fr; height: calc(100vh - 60px); }}
      .player-section {{ height: 42vh; }}
      .sidebar {{ height: calc(58vh - 60px); }}
    }}
  </style>
</head>
<body>
  <header>
    <a href="/dashboard" class="brand">
      <img src="https://film4k.net/favicon-32.png" alt="Film4k">
      <span>Film4k Live TV</span>
      <span class="badge-live">200+ CHANNELS</span>
    </a>
    <div style="display: flex; gap: 8px;">
      <a href="/film4k/playlist.m3u" class="btn btn-outline" title="Tải file M3U cho TiviMate / VLC">
        <i class="fa-solid fa-file-arrow-down"></i> Tải M3U Playlist
      </a>
      <a href="/dashboard" class="btn btn-primary">
        <i class="fa-solid fa-gauge-high"></i> Dashboard
      </a>
    </div>
  </header>

  <div class="main-layout">
    <div class="player-section">
      <div class="video-wrapper">
        <video id="video-player" controls autoplay playsinline></video>
        
        <!-- Top Left Info Badge -->
        <div id="video-overlay" class="top-left-overlay" style="display: none;">
          <img id="overlay-logo" src="" style="width: 22px; height: 22px; object-fit: contain;">
          <span id="overlay-title" style="font-size: 0.85rem; font-weight: 700;"></span>
          <span style="font-size: 0.7rem; color: #10b981; font-weight: 700; margin-left: 4px;">● LIVE</span>
        </div>

        <!-- Unmute prompt banner -->
        <button id="unmute-banner" class="unmute-btn" style="display: none;" onclick="unmuteAudio()">
          <i class="fa-solid fa-volume-xmark"></i> Bấm để bật âm thanh
        </button>

        <!-- Loading state overlay -->
        <div id="player-loading" class="player-state-overlay">
          <div class="spinner"></div>
          <div id="loading-title" style="font-weight: 700; font-size: 1rem; color: #fff;">Đang kết nối luồng phát...</div>
          <div style="font-size: 0.8rem; color: var(--text-dim); margin-top: 4px;">HLS Live Stream Full HD</div>
        </div>

        <!-- Error state overlay -->
        <div id="player-error" class="player-state-overlay" style="display: none;">
          <i class="fa-solid fa-triangle-exclamation" style="font-size: 2.2rem; color: #f87171; margin-bottom: 12px;"></i>
          <div id="error-message" style="font-weight: 700; font-size: 1rem; color: #f87171;">Không thể tải luồng phát</div>
          <div style="font-size: 0.8rem; color: var(--text-dim); margin-top: 6px; max-width: 320px;">Kênh này tạm thời gián đoạn hoặc yêu cầu làm mới Cookie Film4k.</div>
          <button class="btn btn-outline" style="margin-top: 14px;" onclick="retryPlayback()">
            <i class="fa-solid fa-rotate-right"></i> Thử lại
          </button>
        </div>
      </div>

      <div class="channel-info-bar">
        <div>
          <div id="current-title" class="channel-title">Chọn một kênh để bắt đầu xem</div>
          <div id="current-category" class="channel-meta">200+ Kênh Truyền Hình Trực Tiếp & Sự Kiện Thể Thao</div>
        </div>
        <div style="display: flex; gap: 8px;">
          <button class="btn btn-outline" onclick="retryPlayback()" title="Kết nối lại luồng phát">
            <i class="fa-solid fa-rotate"></i> Tải lại
          </button>
          <button id="btn-copy-stream" class="btn btn-outline" onclick="copyCurrentStreamUrl()">
            <i class="fa-solid fa-link"></i> Copy URL
          </button>
        </div>
      </div>
    </div>

    <div class="sidebar">
      <div class="sidebar-controls">
        <input type="text" id="search-input" class="search-box" placeholder="🔍 Tìm kiếm kênh (VTV, K+, HBO, Bóng đá...)..." oninput="renderChannels()">
        <div class="genre-scroll" id="genre-container"></div>
      </div>
      <div class="channel-list" id="channel-list-container"></div>
    </div>
  </div>

  <script>
    const CHANNELS = {channels_json};
    const EVENTS = {events_json};
    let currentGenre = "Tất cả";
    let activeItem = null;
    let shakaPlayer = null;
    let hlsPlayer = null;
    let currentStreamUrl = "";

    // Initialize Shaka polyfills once
    if (window.shaka) {{
      shaka.polyfill.installAll();
    }}

    const GENRES = [
      "Tất cả", "Sự Kiện Trực Tiếp", "VTV", "HTV / HTVC", "K+ Truyền Hình",
      "Thể Thao", "Phim & Điện Ảnh", "Thiếu Nhi & Hoạt Hình", "Khoa Học & Khám Phá",
      "Tin Tức & Thời Sự", "Âm Nhạc & Giải Trí", "VTC", "Đài Địa Phương", "Kênh Quốc Tế & Tổng Hợp"
    ];

    function initGenres() {{
      const container = document.getElementById("genre-container");
      container.innerHTML = "";
      GENRES.forEach(g => {{
        const pill = document.createElement("div");
        pill.className = `genre-pill ${{g === currentGenre ? "active" : ""}}`;
        pill.innerText = g;
        pill.onclick = () => {{
          currentGenre = g;
          document.querySelectorAll(".genre-pill").forEach(p => p.classList.remove("active"));
          pill.classList.add("active");
          renderChannels();
        }};
        container.appendChild(pill);
      }});
    }}

    function renderChannels() {{
      const query = document.getElementById("search-input").value.toLowerCase().trim();
      const container = document.getElementById("channel-list-container");
      container.innerHTML = "";

      let items = [];

      if (currentGenre === "Tất cả" || currentGenre === "Sự Kiện Trực Tiếp") {{
        EVENTS.forEach(ev => {{
          items.push({{
            id: ev.id,
            name: ev.title || "Sự kiện trực tiếp",
            logo: ev.image,
            category: "Sự Kiện Trực Tiếp",
            isEvent: true,
            status: ev.status || "live"
          }});
        }});
      }}

      if (currentGenre !== "Sự Kiện Trực Tiếp") {{
        CHANNELS.forEach(ch => {{
          if (currentGenre === "Tất cả" || ch.category === currentGenre) {{
            items.push(ch);
          }}
        }});
      }}

      if (query) {{
        items = items.filter(it => (it.name || "").toLowerCase().includes(query) || (it.id || "").toLowerCase().includes(query));
      }}

      items.forEach(it => {{
        const isSelected = activeItem && activeItem.id === it.id;
        const div = document.createElement("div");
        div.className = `channel-item ${{isSelected ? "active" : ""}}`;
        div.onclick = () => playItem(it);

        const logoHtml = it.logo
          ? `<img class="channel-logo" src="${{it.logo}}" alt="${{it.name}}" loading="lazy" onerror="this.outerHTML='<div class=\\'channel-fallback\\'>${{it.name.slice(0,3)}}</div>'">`
          : `<div class="channel-fallback">${{it.name.slice(0,3)}}</div>`;

        const badgeHtml = it.isEvent ? `<span style="color: #ef4444; font-weight: 700; font-size: 0.7rem;">[${{it.status.toUpperCase()}}]</span> ` : "";
        const eqHtml = isSelected ? `<div class="playing-eq"><span></span><span></span><span></span></div>` : "";

        div.innerHTML = `
          ${{logoHtml}}
          <div class="channel-details">
            <div class="channel-name" style="display: flex; align-items: center; justify-content: space-between;">
              <span>${{badgeHtml}}${{it.name}}</span>
              ${{eqHtml}}
            </div>
            <div class="channel-cat">${{it.category}}</div>
          </div>
        `;
        container.appendChild(div);
      }});
    }}

    function showLoading(title) {{
      document.getElementById("player-loading").style.display = "flex";
      document.getElementById("player-error").style.display = "none";
      document.getElementById("loading-title").innerText = "Đang kết nối " + (title || "kênh") + "...";
    }}

    function hideLoading() {{
      document.getElementById("player-loading").style.display = "none";
    }}

    function showError(msg) {{
      hideLoading();
      document.getElementById("player-error").style.display = "flex";
      document.getElementById("error-message").innerText = msg || "Không thể tải luồng phát";
    }}

    function checkMuted() {{
      const video = document.getElementById("video-player");
      const banner = document.getElementById("unmute-banner");
      if (video.muted) {{
        banner.style.display = "flex";
      }} else {{
        banner.style.display = "none";
      }}
    }}

    function unmuteAudio() {{
      const video = document.getElementById("video-player");
      video.muted = false;
      video.volume = 1.0;
      document.getElementById("unmute-banner").style.display = "none";
    }}

    async function destroyCurrentPlayer() {{
      if (shakaPlayer) {{
        try {{
          await shakaPlayer.destroy();
        }} catch (e) {{
          console.warn("Error destroying Shaka player:", e);
        }}
        shakaPlayer = null;
      }}
      if (hlsPlayer) {{
        try {{
          hlsPlayer.destroy();
        }} catch (e) {{
          console.warn("Error destroying HLS player:", e);
        }}
        hlsPlayer = null;
      }}
      const video = document.getElementById("video-player");
      video.removeAttribute("src");
      video.load();
    }}

    async function playItem(item) {{
      if (!item) return;
      activeItem = item;
      renderChannels();

      document.getElementById("current-title").innerText = item.name;
      document.getElementById("current-category").innerText = item.category;

      const video = document.getElementById("video-player");
      const overlay = document.getElementById("video-overlay");
      const overlayTitle = document.getElementById("overlay-title");
      const overlayLogo = document.getElementById("overlay-logo");

      overlayTitle.innerText = item.name;
      if (item.logo) {{
        overlayLogo.src = item.logo;
        overlayLogo.style.display = "block";
      }} else {{
        overlayLogo.style.display = "none";
      }}
      overlay.style.display = "flex";

      showLoading(item.name);
      await destroyCurrentPlayer();

      try {{
        const r = await fetch(`/film4k/stream/tv/${{encodeURIComponent(item.id)}}.json`);
        const data = await r.json();
        const stream = data.streams && data.streams[0];

        if (!stream || !stream.url || !stream.url.startsWith("http")) {{
          showError("Kênh tạm thời gián đoạn hoặc chưa có luồng phát.");
          return;
        }}

        currentStreamUrl = stream.url;
        console.log("Playing stream URL:", currentStreamUrl);

        const clearKey = stream.behaviorHints ? stream.behaviorHints.clearKey : null;
        const clearKeys = stream.behaviorHints ? stream.behaviorHints.clearKeys : null;

        // 1. Shaka Player Engine (DASH .mpd, HLS .m3u8, and ClearKey DRM)
        if (window.shaka && shaka.Player.isBrowserSupported()) {{
          shakaPlayer = new shaka.Player(video);

          shakaPlayer.addEventListener("error", (event) => {{
            console.error("Shaka Player Error:", event.detail);
            showError("Lỗi phát luồng: " + (event.detail && event.detail.message ? event.detail.message : "Không thể tải kênh"));
          }});

          const drmConfig = {{}};
          if (clearKey && clearKey.keyId && clearKey.key) {{
            drmConfig.clearKeys = {{
              [clearKey.keyId]: clearKey.key
            }};
          }} else if (clearKeys && typeof clearKeys === "object") {{
            drmConfig.clearKeys = clearKeys;
          }}

          shakaPlayer.configure({{
            drm: drmConfig,
            streaming: {{
              lowLatencyMode: true,
              bufferingGoal: 6,
              rebufferingGoal: 2,
              bufferBehind: 15
            }}
          }});

          try {{
            await shakaPlayer.load(currentStreamUrl);
            hideLoading();
            video.muted = true;
            video.play().then(() => {{
              checkMuted();
            }}).catch(err => {{
              console.log("Autoplay waiting for user gesture:", err);
            }});
            return;
          }} catch (shakaErr) {{
            console.warn("Shaka load failed, trying Hls.js fallback:", shakaErr);
          }}
        }}

        // 2. HLS.js fallback for HLS .m3u8 streams
        if (window.Hls && Hls.isSupported() && !currentStreamUrl.includes(".mpd")) {{
          hlsPlayer = new Hls({{
            enableWorker: true,
            lowLatencyMode: true,
            backBufferLength: 20,
            maxBufferLength: 6,
            maxMaxBufferLength: 12
          }});
          hlsPlayer.loadSource(currentStreamUrl);
          hlsPlayer.attachMedia(video);
          hlsPlayer.on(Hls.Events.MANIFEST_PARSED, function() {{
            hideLoading();
            video.muted = true;
            video.play().then(() => checkMuted()).catch(e => console.log(e));
          }});
          hlsPlayer.on(Hls.Events.ERROR, function(event, data) {{
            if (data.fatal) {{
              showError("Lỗi luồng phát HLS.");
            }}
          }});
          return;
        }}

        // 3. Fallback native
        video.src = currentStreamUrl;
        video.muted = true;
        video.play().then(() => {{
          hideLoading();
          checkMuted();
        }}).catch(e => console.log("Native play error:", e));

      }} catch (err) {{
        console.error("Error playing channel:", err);
        showError("Lỗi kết nối: " + err.message);
      }}
    }}

    function retryPlayback() {{
      if (activeItem) {{
        playItem(activeItem);
      }}
    }}

    function copyCurrentStreamUrl() {{
      if (!currentStreamUrl) {{
        alert("Chưa chọn kênh phát!");
        return;
      }}
      navigator.clipboard.writeText(currentStreamUrl);
      const btn = document.getElementById("btn-copy-stream");
      const old = btn.innerHTML;
      btn.innerHTML = '<i class="fa-solid fa-check"></i> Đã copy!';
      setTimeout(() => btn.innerHTML = old, 2000);
    }}

    // Video event listeners
    const videoElem = document.getElementById("video-player");
    videoElem.addEventListener("playing", () => {{
      hideLoading();
      checkMuted();
    }});
    videoElem.addEventListener("volumechange", checkMuted);

    // Initialize
    initGenres();
    renderChannels();
    // Default to VTV1 HD
    const vtv1 = CHANNELS.find(c => c.id === 'vtv1-hd') || CHANNELS[0];
    if (vtv1) {{
      playItem(vtv1);
    }}
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html)

