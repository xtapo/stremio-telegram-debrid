import asyncio
import json
import logging
import os
import re
import time
import unicodedata
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

from config import Config

logger = logging.getLogger("iptv_router")

iptv_router = APIRouter(prefix="", tags=["iptv"])

# ------------------------------------------------------------------
# Cache & Memory Management
# ------------------------------------------------------------------
_iptv_cache: Dict[str, Tuple[Any, float]] = {}
_channels_by_id: Dict[str, Dict[str, Any]] = {}

COUNTRY_CACHE_TTL = 86400  # 24 hours
PLAYLIST_CACHE_TTL = 43200  # 12 hours

# ------------------------------------------------------------------
# Default Curated Countries with Flag & Name mapping
# ------------------------------------------------------------------
POPULAR_COUNTRIES: List[Dict[str, str]] = [
    {"code": "VN", "name": "Việt Nam", "flag": "🇻🇳"},
    {"code": "US", "name": "United States", "flag": "🇺🇸"},
    {"code": "UK", "name": "United Kingdom", "flag": "🇬🇧"},
    {"code": "JP", "name": "Nhật Bản (Japan)", "flag": "🇯🇵"},
    {"code": "KR", "name": "Hàn Quốc (South Korea)", "flag": "🇰🇷"},
    {"code": "FR", "name": "Pháp (France)", "flag": "🇫🇷"},
    {"code": "DE", "name": "Đức (Germany)", "flag": "🇩🇪"},
    {"code": "CN", "name": "Trung Quốc (China)", "flag": "🇨🇳"},
    {"code": "TH", "name": "Thái Lan (Thailand)", "flag": "🇹🇭"},
    {"code": "SG", "name": "Singapore", "flag": "🇸🇬"},
    {"code": "CA", "name": "Canada", "flag": "🇨🇦"},
    {"code": "AU", "name": "Úc (Australia)", "flag": "🇦🇺"},
    {"code": "ES", "name": "Tây Ban Nha (Spain)", "flag": "🇪🇸"},
    {"code": "IT", "name": "Ý (Italy)", "flag": "🇮🇹"},
    {"code": "IN", "name": "Ấn Độ (India)", "flag": "🇮🇳"},
    {"code": "BR", "name": "Brazil", "flag": "🇧🇷"},
    {"code": "RU", "name": "Nga (Russia)", "flag": "🇷🇺"},
    {"code": "HK", "name": "Hồng Kông (Hong Kong)", "flag": "🇭🇰"},
    {"code": "TW", "name": "Đài Loan (Taiwan)", "flag": "🇹🇼"},
    {"code": "ID", "name": "Indonesia", "flag": "🇮🇩"},
    {"code": "MY", "name": "Malaysia", "flag": "🇲🇾"},
    {"code": "PH", "name": "Philippines", "flag": "🇵🇭"},
    {"code": "NL", "name": "Hà Lan (Netherlands)", "flag": "🇳🇱"},
    {"code": "PT", "name": "Bồ Đào Nha (Portugal)", "flag": "🇵🇹"},
    {"code": "MX", "name": "Mexico", "flag": "🇲🇽"},
    {"code": "AR", "name": "Argentina", "flag": "🇦🇷"},
    {"code": "TR", "name": "Thổ Nhĩ Kỳ (Turkey)", "flag": "🇹🇷"},
    {"code": "SA", "name": "Saudi Arabia", "flag": "🇸🇦"},
    {"code": "AE", "name": "UAE", "flag": "🇦🇪"},
]

# Quick genre option labels for Stremio
GENRE_OPTIONS = [f"{c['flag']} {c['name']} [{c['code']}]" for c in POPULAR_COUNTRIES]

_country_code_lookup: Dict[str, str] = {}
for c in POPULAR_COUNTRIES:
    _country_code_lookup[c["code"].upper()] = c["code"].lower()
    _country_code_lookup[c["name"].lower()] = c["code"].lower()
    _country_code_lookup[f"{c['flag']} {c['name']} [{c['code']}]".lower()] = c["code"].lower()


_http_client: Optional[httpx.AsyncClient] = None
_client_loop: Optional[asyncio.AbstractEventLoop] = None


def get_http_client() -> httpx.AsyncClient:
    global _http_client, _client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if (
        _http_client is None
        or _http_client.is_closed
        or _client_loop != current_loop
        or (current_loop and current_loop.is_closed())
    ):
        _client_loop = current_loop
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=40, max_connections=100),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            },
        )
    return _http_client


def normalize_text(text: str) -> str:
    """Normalize text for insensitive searching and diacritic removal."""
    if not text:
        return ""
    text = text.lower().strip()
    nfkd = unicodedata.normalize("NFD", text)
    stripped = "".join([c for c in nfkd if unicodedata.category(c) != "Mn"])
    return re.sub(r"[^a-z0-9]", "", stripped)


def parse_country_code_from_filter(genre_or_name: Optional[str]) -> str:
    """Resolve ISO country code from string/genre."""
    if not genre_or_name:
        return "vn"

    cleaned = genre_or_name.strip()
    # Check if format contains [CODE]
    m = re.search(r"\[([A-Za-z]{2})\]", cleaned)
    if m:
        return m.group(1).lower()

    if len(cleaned) == 2 and cleaned.isalpha():
        return cleaned.lower()

    low = cleaned.lower()
    if low in _country_code_lookup:
        return _country_code_lookup[low]

    # Search in all countries
    for code, mapped in _country_code_lookup.items():
        if code in low or low in code:
            return mapped

    return "vn"


# ------------------------------------------------------------------
# Fetch & Parse M3U Playlists from IPTV-Org
# ------------------------------------------------------------------
def parse_m3u_playlist(content: str, country_code: str) -> List[Dict[str, Any]]:
    """Parse M3U string into structured channel metadata list."""
    channels: List[Dict[str, Any]] = []
    lines = content.splitlines()
    curr: Optional[Dict[str, Any]] = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith("#EXTINF:"):
            curr = {}
            tvg_id_m = re.search(r'tvg-id="([^"]*)"', line)
            tvg_name_m = re.search(r'tvg-name="([^"]*)"', line)
            tvg_logo_m = re.search(r'tvg-logo="([^"]*)"', line)
            group_m = re.search(r'group-title="([^"]*)"', line)

            parts = line.split(",", 1)
            raw_title = parts[1].strip() if len(parts) > 1 else "TV Channel"

            # Parse resolution info from title if present
            resolution = "HD"
            if "1080p" in raw_title or "1080i" in raw_title or "FHD" in raw_title:
                resolution = "1080p Full HD"
            elif "720p" in raw_title or "HD" in raw_title:
                resolution = "720p HD"
            elif "4K" in raw_title or "2160p" in raw_title:
                resolution = "4K Ultra HD"
            elif "576p" in raw_title or "480p" in raw_title or "SD" in raw_title:
                resolution = "SD"

            is_geoblocked = "[Geo-blocked]" in raw_title or "[geo-blocked]" in raw_title

            tvg_id = tvg_id_m.group(1) if tvg_id_m else ""
            tvg_name = tvg_name_m.group(1) if tvg_name_m else ""
            logo = tvg_logo_m.group(1) if tvg_logo_m else ""
            group = group_m.group(1) if group_m else "General"
            if not group or group == "Undefined":
                group = "General"

            curr["raw_title"] = raw_title
            curr["title"] = raw_title.replace("[Geo-blocked]", "").replace("[Not 24/7]", "").strip()
            curr["tvg_id"] = tvg_id
            curr["tvg_name"] = tvg_name
            curr["logo"] = logo or "https://raw.githubusercontent.com/iptv-org/iptv/master/banner.png"
            curr["group"] = group
            curr["country"] = country_code.upper()
            curr["resolution"] = resolution
            curr["is_geoblocked"] = is_geoblocked

        elif curr is not None and not line.startswith("#"):
            stream_url = line
            curr["url"] = stream_url

            # Generate unique safe channel ID
            raw_ident = curr["tvg_id"] or curr["title"]
            slug = re.sub(r"[^a-zA-Z0-9]", "_", raw_ident).strip("_").lower()
            if not slug:
                slug = f"ch_{len(channels)}"
            channel_id = f"iptv:{country_code.lower()}:{slug}"
            curr["id"] = channel_id

            # Save in global channels lookup
            _channels_by_id[channel_id] = curr
            channels.append(curr)
            curr = None

    return channels


async def fetch_country_channels(country_code: str) -> List[Dict[str, Any]]:
    """Fetch M3U playlist for a specific country from iptv-org with multi-layer caching."""
    code = (country_code or "vn").lower()
    cache_key = f"playlist:{code}"
    now = time.time()

    if cache_key in _iptv_cache:
        data, exp = _iptv_cache[cache_key]
        if now < exp:
            return data

    # 1. Disk cache fallback
    cache_dir = os.path.join("temp_cache", "iptv")
    os.makedirs(cache_dir, exist_ok=True)
    disk_file = os.path.join(cache_dir, f"{code}.json")

    client = get_http_client()
    urls = [
        f"https://iptv-org.github.io/iptv/countries/{code}.m3u",
        f"https://raw.githubusercontent.com/iptv-org/iptv/master/streams/{code}.m3u",
    ]

    content: Optional[str] = None
    for u in urls:
        try:
            r = await client.get(u)
            if r.status_code == 200 and r.text and "#EXTM3U" in r.text:
                content = r.text
                break
        except Exception as e:
            logger.debug(f"Failed fetching {u}: {e}")

    if content:
        channels = parse_m3u_playlist(content, code)
        if channels:
            _iptv_cache[cache_key] = (channels, now + PLAYLIST_CACHE_TTL)
            # Save to disk asynchronously
            try:
                with open(disk_file, "w", encoding="utf-8") as f:
                    json.dump(channels, f, ensure_ascii=False)
            except Exception:
                pass
            return channels

    # If network fetch failed, load from disk if available
    if os.path.exists(disk_file):
        try:
            with open(disk_file, "r", encoding="utf-8") as f:
                channels = json.load(f)
                for ch in channels:
                    _channels_by_id[ch["id"]] = ch
                _iptv_cache[cache_key] = (channels, now + 3600)
                return channels
        except Exception as e:
            logger.warning(f"Failed loading disk cache for {code}: {e}")

    return []


async def fetch_all_countries_list() -> List[Dict[str, Any]]:
    """Fetch complete list of 200+ countries from iptv-org API."""
    cache_key = "all_countries"
    now = time.time()

    if cache_key in _iptv_cache:
        data, exp = _iptv_cache[cache_key]
        if now < exp:
            return data

    client = get_http_client()
    url = "https://iptv-org.github.io/api/countries.json"
    try:
        r = await client.get(url)
        if r.status_code == 200:
            countries = r.json()
            if isinstance(countries, list) and len(countries) > 0:
                for c in countries:
                    if c.get("code") and c.get("name"):
                        _country_code_lookup[c["code"].upper()] = c["code"].lower()
                        _country_code_lookup[c["name"].lower()] = c["code"].lower()
                _iptv_cache[cache_key] = (countries, now + COUNTRY_CACHE_TTL)
                return countries
    except Exception as e:
        logger.warning(f"Failed fetching all countries from {url}: {e}")

    return POPULAR_COUNTRIES


# ------------------------------------------------------------------
# Stremio Manifest
# ------------------------------------------------------------------
def get_iptv_manifest(api_key: str = "") -> Dict[str, Any]:
    show_on_board = getattr(Config, "ENABLE_BOARD_IPTV", True)
    main_req = not show_on_board

    return {
        "id": "com.stremio.iptv.org",
        "version": "1.0.0",
        "name": "IPTV Org - Kênh TV Chia Theo Quốc Gia",
        "description": "Xem trực tiếp hàng ngàn kênh truyền hình miễn phí từ hơn 200+ quốc gia (Việt Nam 🇻🇳, Mỹ 🇺🇸, Anh 🇬🇧, Nhật Bản 🇯🇵, Hàn Quốc 🇰🇷, Pháp 🇫🇷, v.v.) nguồn mở từ iptv-org/iptv.",
        "logo": "https://raw.githubusercontent.com/iptv-org/iptv/master/banner.png",
        "resources": [
            "catalog",
            {
                "name": "meta",
                "types": ["tv"],
                "idPrefixes": ["iptv:"]
            },
            {
                "name": "stream",
                "types": ["tv"],
                "idPrefixes": ["iptv:"]
            }
        ],
        "types": ["tv"],
        "catalogs": [
            {
                "type": "tv",
                "id": "iptv_channels",
                "name": "IPTV Org - Kênh TV Theo Quốc Gia",
                "extra": [
                    {"name": "genre", "options": GENRE_OPTIONS, "isRequired": main_req},
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
@iptv_router.get("/manifest.json")
@iptv_router.get("/iptv/manifest.json")
@iptv_router.get("/{api_key}/iptv/manifest.json")
async def manifest_endpoint(api_key: str = ""):
    if not getattr(Config, "ENABLE_SOURCE_IPTV", True):
        raise HTTPException(status_code=404, detail="IPTV Org Source is disabled")
    return JSONResponse(get_iptv_manifest(api_key))


# ------------------------------------------------------------------
# Catalog Endpoints
# ------------------------------------------------------------------
@iptv_router.get("/catalog/{type}/{id}.json")
@iptv_router.get("/catalog/{type}/{id}/{extra}.json")
@iptv_router.get("/iptv/catalog/{type}/{id}.json")
@iptv_router.get("/iptv/catalog/{type}/{id}/{extra}.json")
@iptv_router.get("/{api_key}/iptv/catalog/{type}/{id}.json")
@iptv_router.get("/{api_key}/iptv/catalog/{type}/{id}/{extra}.json")
async def catalog_endpoint(
    type: str,
    id: str,
    extra: Optional[str] = None,
    api_key: str = ""
):
    if not getattr(Config, "ENABLE_SOURCE_IPTV", True):
        return JSONResponse({"metas": []})

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

    country_code = parse_country_code_from_filter(genre_filter)
    channels = await fetch_country_channels(country_code)

    metas = []
    country_upper = country_code.upper()

    for ch in channels:
        name = ch.get("title") or ch.get("raw_title") or "Kênh TV"
        ch_id = ch.get("id") or f"iptv:{country_code}:{name}"
        logo = ch.get("logo") or "https://raw.githubusercontent.com/iptv-org/iptv/master/banner.png"
        group = ch.get("group") or "General"
        resolution = ch.get("resolution") or "HD"
        geoblocked = ch.get("is_geoblocked", False)

        # Search filter
        if search_query:
            norm_q = normalize_text(search_query)
            norm_name = normalize_text(name)
            norm_id = normalize_text(ch_id)
            if norm_q not in norm_name and norm_q not in norm_id:
                continue

        geo_badge = " [Geo-blocked]" if geoblocked else ""
        desc = (
            f"📺 Kênh: {name}{geo_badge}\n"
            f"🌐 Quốc gia: {country_upper}\n"
            f"📁 Thể loại: {group}\n"
            f"⚡ Độ phân giải: {resolution}\n"
            f"📡 Nguồn phát: IPTV-Org Public Live Streams"
        )

        metas.append({
            "id": ch_id,
            "type": "tv",
            "name": f"{name} ({country_upper})",
            "poster": logo,
            "background": logo,
            "logo": logo,
            "description": desc,
            "genres": [f"Quốc Gia: {country_upper}", group, "IPTV Org"],
            "posterShape": "square",
        })

    # Pagination
    if skip_val > 0 and skip_val < len(metas):
        metas = metas[skip_val:]

    return JSONResponse({"metas": metas})


# ------------------------------------------------------------------
# Meta Endpoints
# ------------------------------------------------------------------
@iptv_router.get("/meta/{type}/{id}.json")
@iptv_router.get("/iptv/meta/{type}/{id}.json")
@iptv_router.get("/{api_key}/iptv/meta/{type}/{id}.json")
async def meta_endpoint(type: str, id: str, api_key: str = ""):
    if not getattr(Config, "ENABLE_SOURCE_IPTV", True):
        raise HTTPException(status_code=404, detail="IPTV Org is disabled")

    ch = _channels_by_id.get(id)
    if not ch:
        # Try finding country code in id
        parts = id.split(":")
        if len(parts) >= 3:
            country_code = parts[1]
            await fetch_country_channels(country_code)
            ch = _channels_by_id.get(id)

    if ch:
        name = ch.get("title") or "Kênh TV"
        logo = ch.get("logo") or "https://raw.githubusercontent.com/iptv-org/iptv/master/banner.png"
        group = ch.get("group") or "General"
        country = ch.get("country") or "Global"
        resolution = ch.get("resolution") or "HD"

        return JSONResponse({
            "meta": {
                "id": id,
                "type": "tv",
                "name": f"{name} ({country})",
                "poster": logo,
                "background": logo,
                "logo": logo,
                "description": (
                    f"Kênh truyền hình trực tiếp {name}\n"
                    f"Quốc gia: {country} | Thể loại: {group} | Chuẩn phát: {resolution}\n"
                    f"Nguồn: IPTV-Org Live Streaming Network"
                ),
                "genres": [f"Quốc Gia: {country}", group, "Live TV"],
                "posterShape": "square"
            }
        })

    # Fallback generic meta
    return JSONResponse({
        "meta": {
            "id": id,
            "type": "tv",
            "name": f"Kênh TV {id}",
            "poster": "https://raw.githubusercontent.com/iptv-org/iptv/master/banner.png",
            "description": "Kênh truyền hình IPTV Org",
            "genres": ["Live TV", "IPTV"]
        }
    })


# ------------------------------------------------------------------
# Stream Endpoints
# ------------------------------------------------------------------
@iptv_router.get("/stream/{type}/{id}.json")
@iptv_router.get("/iptv/stream/{type}/{id}.json")
@iptv_router.get("/{api_key}/iptv/stream/{type}/{id}.json")
async def stream_endpoint(request: Request, type: str, id: str, api_key: str = ""):
    if not getattr(Config, "ENABLE_SOURCE_IPTV", True):
        return JSONResponse({"streams": []})

    ch = _channels_by_id.get(id)
    if not ch:
        parts = id.split(":")
        if len(parts) >= 3:
            country_code = parts[1]
            await fetch_country_channels(country_code)
            ch = _channels_by_id.get(id)

    if not ch or not ch.get("url"):
        return JSONResponse({"streams": []})

    stream_url = ch["url"]
    name = ch.get("title") or "Kênh TV"
    resolution = ch.get("resolution") or "Live HLS"
    country = ch.get("country") or "VN"

    streams = [
        {
            "name": f"IPTV [{country}] • {resolution}",
            "title": f"⚡ {name}\n[Luồng Trực Tiếp M3U8 • Nguồn IPTV-Org • {resolution}]",
            "url": stream_url,
            "behaviorHints": {
                "notWebReady": False,
                "proxyHeaders": {
                    "request": {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Referer": "https://iptv-org.github.io/"
                    }
                }
            }
        }
    ]

    return JSONResponse({"streams": streams})


# ------------------------------------------------------------------
# JSON API for Web TV Player
# ------------------------------------------------------------------
@iptv_router.get("/api/countries")
@iptv_router.get("/iptv/api/countries")
async def api_countries():
    countries = await fetch_all_countries_list()
    return JSONResponse({"countries": countries, "popular": POPULAR_COUNTRIES})


@iptv_router.get("/api/channels")
@iptv_router.get("/iptv/api/channels")
async def api_channels(country: str = Query("vn", description="Country ISO code")):
    channels = await fetch_country_channels(country)
    return JSONResponse({
        "country": country.upper(),
        "total": len(channels),
        "channels": channels
    })


# ------------------------------------------------------------------
# Web TV Player UI (/iptv/tv, /iptv/player, /iptv)
# ------------------------------------------------------------------
@iptv_router.get("/tv", response_class=HTMLResponse)
@iptv_router.get("/player", response_class=HTMLResponse)
@iptv_router.get("/iptv/tv", response_class=HTMLResponse)
@iptv_router.get("/iptv/player", response_class=HTMLResponse)
@iptv_router.get("/iptv", response_class=HTMLResponse)
async def web_tv_player_page(request: Request, country: Optional[str] = "vn", ch: Optional[str] = None):
    """Modern Glassmorphism Web TV Player for IPTV-Org Channels Worldwide."""
    host = request.headers.get("host") or f"127.0.0.1:{Config.PORT}"
    scheme = request.url.scheme
    manifest_url = f"{scheme}://{host}/iptv/manifest.json"
    stremio_link = manifest_url.replace("http://", "stremio://").replace("https://", "stremio://")

    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IPTV Org Global - Truyền Hình Trực Tiếp Theo Quốc Gia</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <style>
        :root {{
            --bg-base: #090c15;
            --bg-card: rgba(18, 24, 38, 0.75);
            --bg-card-hover: rgba(28, 38, 60, 0.85);
            --bg-accent: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 50%, #ec4899 100%);
            --accent-glow: rgba(59, 130, 246, 0.4);
            --text-main: #f3f4f6;
            --text-sub: #9ca3af;
            --border-color: rgba(255, 255, 255, 0.08);
            --border-focus: rgba(99, 102, 241, 0.5);
            --radius-lg: 16px;
            --radius-md: 12px;
            --radius-sm: 8px;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Outfit', sans-serif;
            -webkit-tap-highlight-color: transparent;
        }}

        body {{
            background: var(--bg-base);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
            background-image: 
                radial-gradient(at 0% 0%, rgba(59, 130, 246, 0.15) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(236, 72, 153, 0.12) 0px, transparent 50%),
                radial-gradient(at 50% 50%, rgba(139, 92, 246, 0.08) 0px, transparent 50%);
            background-attachment: fixed;
        }}

        /* Header */
        header {{
            position: sticky;
            top: 0;
            z-index: 100;
            backdrop-filter: blur(20px);
            background: rgba(9, 12, 21, 0.85);
            border-bottom: 1px solid var(--border-color);
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
        }}

        .logo-area {{
            display: flex;
            align-items: center;
            gap: 12px;
            text-decoration: none;
            color: var(--text-main);
        }}

        .logo-badge {{
            width: 42px;
            height: 42px;
            border-radius: var(--radius-md);
            background: var(--bg-accent);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            box-shadow: 0 4px 20px var(--accent-glow);
        }}

        .logo-text h1 {{
            font-size: 1.25rem;
            font-weight: 700;
            letter-spacing: -0.5px;
            background: linear-gradient(90deg, #fff, #93c5fd);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .logo-text p {{
            font-size: 0.75rem;
            color: var(--text-sub);
        }}

        .header-actions {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            border-radius: var(--radius-md);
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            text-decoration: none;
            border: none;
        }}

        .btn-stremio {{
            background: linear-gradient(135deg, #7c3aed, #4f46e5);
            color: #fff;
            box-shadow: 0 4px 15px rgba(124, 58, 237, 0.35);
        }}

        .btn-stremio:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(124, 58, 237, 0.5);
        }}

        .btn-copy {{
            background: rgba(255, 255, 255, 0.08);
            color: var(--text-main);
            border: 1px solid var(--border-color);
        }}

        .btn-copy:hover {{
            background: rgba(255, 255, 255, 0.15);
        }}

        /* Main Layout */
        .main-container {{
            display: grid;
            grid-template-columns: 1fr 380px;
            gap: 20px;
            padding: 20px 24px;
            max-width: 1800px;
            margin: 0 auto;
            width: 100%;
            flex: 1;
        }}

        @media (max-width: 1080px) {{
            .main-container {{
                grid-template-columns: 1fr;
            }}
        }}

        /* Video Area */
        .player-section {{
            display: flex;
            flex-direction: column;
            gap: 16px;
            min-width: 0;
        }}

        .video-wrapper {{
            position: relative;
            width: 100%;
            padding-top: 56.25%; /* 16:9 */
            background: #000;
            border-radius: var(--radius-lg);
            overflow: hidden;
            border: 1px solid var(--border-color);
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.6);
        }}

        #videoPlayer {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: contain;
        }}

        .player-overlay {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.85);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 14px;
            z-index: 10;
            transition: opacity 0.3s ease;
        }}

        .player-overlay.hidden {{
            opacity: 0;
            pointer-events: none;
        }}

        .player-info-card {{
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
        }}

        .channel-main-info {{
            display: flex;
            align-items: center;
            gap: 16px;
        }}

        .channel-avatar {{
            width: 56px;
            height: 56px;
            border-radius: var(--radius-md);
            background: #1e293b;
            padding: 6px;
            object-fit: contain;
            border: 1px solid var(--border-color);
        }}

        .channel-titles h2 {{
            font-size: 1.3rem;
            font-weight: 700;
            color: #fff;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .badge-live {{
            background: #ef4444;
            color: #fff;
            font-size: 0.7rem;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 20px;
            animation: pulse 1.5s infinite;
        }}

        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}

        .channel-meta-tags {{
            display: flex;
            gap: 8px;
            margin-top: 6px;
            flex-wrap: wrap;
        }}

        .meta-tag {{
            font-size: 0.75rem;
            background: rgba(255, 255, 255, 0.08);
            padding: 3px 10px;
            border-radius: 20px;
            color: var(--text-sub);
        }}

        /* Country Navigation Bar */
        .country-nav {{
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            padding: 14px 18px;
            display: flex;
            align-items: center;
            gap: 12px;
            overflow-x: auto;
            scrollbar-width: thin;
        }}

        .country-nav::-webkit-scrollbar {{
            height: 4px;
        }}

        .country-nav::-webkit-scrollbar-thumb {{
            background: rgba(255, 255, 255, 0.2);
            border-radius: 4px;
        }}

        .country-pill {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 16px;
            border-radius: 30px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            color: var(--text-sub);
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
            transition: all 0.2s ease;
        }}

        .country-pill:hover {{
            background: rgba(255, 255, 255, 0.12);
            color: #fff;
            transform: translateY(-1px);
        }}

        .country-pill.active {{
            background: var(--bg-accent);
            color: #fff;
            border-color: transparent;
            box-shadow: 0 4px 16px var(--accent-glow);
        }}

        .country-dropdown-select {{
            background: #1e293b;
            color: #fff;
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 8px 14px;
            font-size: 0.85rem;
            outline: none;
            cursor: pointer;
        }}

        /* Sidebar Channel List */
        .sidebar-section {{
            display: flex;
            flex-direction: column;
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            padding: 18px;
            height: calc(100vh - 120px);
            position: sticky;
            top: 80px;
        }}

        @media (max-width: 1080px) {{
            .sidebar-section {{
                height: 500px;
                position: static;
            }}
        }}

        .sidebar-header {{
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-bottom: 14px;
        }}

        .search-box {{
            position: relative;
            width: 100%;
        }}

        .search-box i {{
            position: absolute;
            left: 14px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-sub);
            font-size: 0.9rem;
        }}

        .search-input {{
            width: 100%;
            padding: 10px 14px 10px 38px;
            background: rgba(0, 0, 0, 0.35);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            color: #fff;
            font-size: 0.9rem;
            outline: none;
            transition: border-color 0.2s;
        }}

        .search-input:focus {{
            border-color: #6366f1;
        }}

        .category-filter-bar {{
            display: flex;
            gap: 6px;
            overflow-x: auto;
            padding-bottom: 4px;
            scrollbar-width: none;
        }}

        .cat-chip {{
            font-size: 0.75rem;
            padding: 4px 10px;
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.06);
            color: var(--text-sub);
            cursor: pointer;
            white-space: nowrap;
            border: 1px solid transparent;
        }}

        .cat-chip.active {{
            background: #3b82f6;
            color: #fff;
        }}

        .channel-list {{
            flex: 1;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 8px;
            padding-right: 4px;
            scrollbar-width: thin;
        }}

        .channel-list::-webkit-scrollbar {{
            width: 5px;
        }}

        .channel-list::-webkit-scrollbar-thumb {{
            background: rgba(255, 255, 255, 0.15);
            border-radius: 4px;
        }}

        .channel-item {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 12px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .channel-item:hover {{
            background: var(--bg-card-hover);
            transform: translateX(3px);
            border-color: rgba(99, 102, 241, 0.3);
        }}

        .channel-item.active {{
            background: rgba(59, 130, 246, 0.15);
            border-color: #3b82f6;
            box-shadow: inset 3px 0 0 #3b82f6;
        }}

        .channel-item img {{
            width: 38px;
            height: 38px;
            border-radius: var(--radius-sm);
            background: #1e293b;
            object-fit: contain;
            padding: 3px;
        }}

        .channel-item-details {{
            flex: 1;
            min-width: 0;
        }}

        .channel-item-name {{
            font-size: 0.9rem;
            font-weight: 600;
            color: #fff;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .channel-item-sub {{
            font-size: 0.75rem;
            color: var(--text-sub);
            display: flex;
            gap: 6px;
            margin-top: 2px;
        }}

        .res-badge {{
            font-size: 0.65rem;
            background: rgba(255, 255, 255, 0.1);
            padding: 1px 6px;
            border-radius: 4px;
            color: #93c5fd;
        }}

        /* Toast notification */
        .toast {{
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: #10b981;
            color: #fff;
            padding: 12px 20px;
            border-radius: var(--radius-md);
            font-size: 0.9rem;
            font-weight: 600;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            display: flex;
            align-items: center;
            gap: 8px;
            transform: translateY(100px);
            opacity: 0;
            transition: all 0.3s ease;
            z-index: 1000;
        }}

        .toast.show {{
            transform: translateY(0);
            opacity: 1;
        }}
    </style>
</head>
<body>

    <!-- Header -->
    <header>
        <a href="/iptv/tv" class="logo-area">
            <div class="logo-badge">
                <i class="fa-solid fa-satellite-dish"></i>
            </div>
            <div class="logo-text">
                <h1>IPTV ORG GLOBAL</h1>
                <p>200+ Quốc Gia • Miễn Phí • Trực Tiếp M3U8</p>
            </div>
        </a>

        <div class="header-actions">
            <button class="btn btn-copy" onclick="copyManifestUrl()">
                <i class="fa-regular fa-clone"></i> Copy Manifest
            </button>
            <a href="{stremio_link}" class="btn btn-stremio">
                <i class="fa-solid fa-play"></i> Thêm vào Stremio
            </a>
        </div>
    </header>

    <!-- Main Body Container -->
    <div class="main-container">
        
        <!-- Left: Video Area & Country Switcher -->
        <div class="player-section">
            <!-- Video Player -->
            <div class="video-wrapper">
                <video id="videoPlayer" controls autoplay playsinline></video>
                <div id="playerOverlay" class="player-overlay">
                    <i class="fa-solid fa-circle-notch fa-spin fa-2x" style="color: #60a5fa;"></i>
                    <p id="overlayText">Đang kết nối luồng phát...</p>
                </div>
            </div>

            <!-- Current Playing Channel Info -->
            <div class="player-info-card">
                <div class="channel-main-info">
                    <img id="currentLogo" class="channel-avatar" src="https://raw.githubusercontent.com/iptv-org/iptv/master/banner.png" alt="Channel Logo">
                    <div class="channel-titles">
                        <h2 id="currentTitle">Chọn một kênh để phát <span class="badge-live">LIVE</span></h2>
                        <div class="channel-meta-tags">
                            <span id="currentCountry" class="meta-tag">🌐 Quốc Gia: VN</span>
                            <span id="currentGroup" class="meta-tag">📁 Thể Loại: General</span>
                            <span id="currentRes" class="meta-tag">⚡ Độ phân giải: HD</span>
                        </div>
                    </div>
                </div>
                <div>
                    <button class="btn btn-copy" onclick="reloadStream()" title="Làm mới luồng">
                        <i class="fa-solid fa-rotate-right"></i>
                    </button>
                </div>
            </div>

            <!-- Horizontal Country Pills Navigation -->
            <div class="country-nav" id="countryNav">
                <!-- Injected via JS -->
            </div>
        </div>

        <!-- Right: Channel List Sidebar -->
        <div class="sidebar-section">
            <div class="sidebar-header">
                <div class="search-box">
                    <i class="fa-solid fa-magnifying-glass"></i>
                    <input type="text" id="searchInput" class="search-input" placeholder="Tìm kiếm kênh trong nước này..." oninput="onSearchInput()">
                </div>
                <div class="category-filter-bar" id="categoryFilterBar">
                    <span class="cat-chip active" onclick="filterCategory('All')">Tất cả</span>
                </div>
            </div>

            <!-- List of Channels -->
            <div class="channel-list" id="channelList">
                <div style="text-align:center; padding: 40px; color: var(--text-sub);">
                    <i class="fa-solid fa-spinner fa-spin fa-2x"></i>
                    <p style="margin-top: 10px;">Đang tải danh sách kênh...</p>
                </div>
            </div>
        </div>

    </div>

    <!-- Toast Notification -->
    <div id="toast" class="toast">
        <i class="fa-solid fa-check-circle"></i>
        <span id="toastMsg">Đã sao chép liên kết Manifest!</span>
    </div>

    <script>
        const MANIFEST_URL = "{manifest_url}";
        let currentCountry = "{country or 'vn'}".toLowerCase();
        let allChannels = [];
        let filteredChannels = [];
        let selectedCategory = "All";
        let activeChannel = null;
        let hlsInstance = null;

        const popularCountries = {json.dumps(POPULAR_COUNTRIES)};

        // Initialize App
        document.addEventListener("DOMContentLoaded", () => {{
            renderCountryNav();
            loadChannels(currentCountry);
        }});

        function renderCountryNav() {{
            const nav = document.getElementById("countryNav");
            let html = "";
            popularCountries.forEach(c => {{
                const isActive = c.code.toLowerCase() === currentCountry;
                html += `
                    <div class="country-pill ${{isActive ? 'active' : ''}}" onclick="switchCountry('${{c.code.toLowerCase()}}')">
                        <span>${{c.flag}}</span>
                        <span>${{c.name}}</span>
                    </div>
                `;
            }});

            html += `
                <select class="country-dropdown-select" onchange="switchCountry(this.value)">
                    <option value="">➕ Chọn quốc gia khác...</option>
                    <option value="ar">🇦🇷 Argentina</option>
                    <option value="au">🇦🇺 Australia</option>
                    <option value="br">🇧🇷 Brazil</option>
                    <option value="ca">🇨🇦 Canada</option>
                    <option value="cn">🇨🇳 China</option>
                    <option value="de">🇩🇪 Germany</option>
                    <option value="es">🇪🇸 Spain</option>
                    <option value="fr">🇫🇷 France</option>
                    <option value="uk">🇬🇧 United Kingdom</option>
                    <option value="hk">🇭🇰 Hong Kong</option>
                    <option value="id">🇮🇩 Indonesia</option>
                    <option value="in">🇮🇳 India</option>
                    <option value="it">🇮🇹 Italy</option>
                    <option value="jp">🇯🇵 Japan</option>
                    <option value="kr">🇰🇷 South Korea</option>
                    <option value="my">🇲🇾 Malaysia</option>
                    <option value="mx">🇲🇽 Mexico</option>
                    <option value="nl">🇳🇱 Netherlands</option>
                    <option value="ph">🇵🇭 Philippines</option>
                    <option value="pt">🇵🇹 Portugal</option>
                    <option value="ru">🇷🇺 Russia</option>
                    <option value="sa">🇸🇦 Saudi Arabia</option>
                    <option value="sg">🇸🇬 Singapore</option>
                    <option value="th">🇹🇭 Thailand</option>
                    <option value="tr">🇹🇷 Turkey</option>
                    <option value="tw">🇹🇼 Taiwan</option>
                    <option value="us">🇺🇸 United States</option>
                    <option value="vn">🇻🇳 Vietnam</option>
                </select>
            `;
            nav.innerHTML = html;
        }}

        async function switchCountry(code) {{
            if (!code) return;
            currentCountry = code.toLowerCase();
            renderCountryNav();
            document.getElementById("searchInput").value = "";
            selectedCategory = "All";
            await loadChannels(currentCountry);
        }}

        async function loadChannels(countryCode) {{
            const listEl = document.getElementById("channelList");
            listEl.innerHTML = `
                <div style="text-align:center; padding: 40px; color: var(--text-sub);">
                    <i class="fa-solid fa-spinner fa-spin fa-2x"></i>
                    <p style="margin-top: 10px;">Đang tải kênh ${{countryCode.toUpperCase()}}...</p>
                </div>
            `;

            try {{
                const res = await fetch(`/iptv/api/channels?country=${{countryCode}}`);
                const data = await res.json();
                allChannels = data.channels || [];
                extractCategories();
                renderCategoryChips();
                filterAndRenderChannels();

                // Auto play first channel if available
                if (allChannels.length > 0) {{
                    playChannel(allChannels[0]);
                }} else {{
                    document.getElementById("overlayText").innerText = "Không tìm thấy kênh phát.";
                }}
            }} catch (e) {{
                listEl.innerHTML = `<div style="text-align:center; padding: 30px; color: #ef4444;">Lỗi tải dữ liệu kênh.</div>`;
            }}
        }}

        function extractCategories() {{
            const categories = new Set(["All"]);
            allChannels.forEach(c => {{
                if (c.group) {{
                    c.group.split(";").forEach(g => categories.add(g.trim()));
                }}
            }});
            window.extractedCategories = Array.from(categories);
        }}

        function renderCategoryChips() {{
            const container = document.getElementById("categoryFilterBar");
            let html = `<span class="cat-chip ${{selectedCategory === 'All' ? 'active' : ''}}" onclick="filterCategory('All')">Tất cả</span>`;
            if (window.extractedCategories) {{
                window.extractedCategories.filter(c => c !== "All").forEach(cat => {{
                    const isActive = selectedCategory === cat;
                    html += `<span class="cat-chip ${{isActive ? 'active' : ''}}" onclick="filterCategory('${{cat}}')">${{cat}}</span>`;
                }});
            }}
            container.innerHTML = html;
        }}

        function filterCategory(cat) {{
            selectedCategory = cat;
            renderCategoryChips();
            filterAndRenderChannels();
        }}

        function onSearchInput() {{
            filterAndRenderChannels();
        }}

        function filterAndRenderChannels() {{
            const q = document.getElementById("searchInput").value.toLowerCase().trim();
            filteredChannels = allChannels.filter(c => {{
                const matchesCat = selectedCategory === "All" || (c.group && c.group.includes(selectedCategory));
                const matchesQuery = !q || c.title.toLowerCase().includes(q) || (c.tvg_id && c.tvg_id.toLowerCase().includes(q));
                return matchesCat && matchesQuery;
            }});

            const listEl = document.getElementById("channelList");
            if (filteredChannels.length === 0) {{
                listEl.innerHTML = `<div style="text-align:center; padding: 40px; color: var(--text-sub);">Không có kênh nào phù hợp.</div>`;
                return;
            }}

            let html = "";
            filteredChannels.forEach(c => {{
                const isActive = activeChannel && activeChannel.id === c.id;
                const logo = c.logo || "https://raw.githubusercontent.com/iptv-org/iptv/master/banner.png";
                html += `
                    <div class="channel-item ${{isActive ? 'active' : ''}}" onclick='playChannelById("${{c.id}}")'>
                        <img src="${{logo}}" onerror="this.src='https://raw.githubusercontent.com/iptv-org/iptv/master/banner.png'" alt="${{c.title}}">
                        <div class="channel-item-details">
                            <div class="channel-item-name">${{c.title}}</div>
                            <div class="channel-item-sub">
                                <span class="res-badge">${{c.resolution || 'HD'}}</span>
                                <span>${{c.group || 'General'}}</span>
                            </div>
                        </div>
                    </div>
                `;
            }});
            listEl.innerHTML = html;
        }}

        function playChannelById(id) {{
            const ch = allChannels.find(c => c.id === id);
            if (ch) playChannel(ch);
        }}

        function playChannel(ch) {{
            activeChannel = ch;
            filterAndRenderChannels();

            document.getElementById("currentTitle").innerHTML = `${{ch.title}} <span class="badge-live">LIVE</span>`;
            document.getElementById("currentLogo").src = ch.logo || "https://raw.githubusercontent.com/iptv-org/iptv/master/banner.png";
            document.getElementById("currentCountry").innerText = `🌐 Quốc Gia: ${{ch.country || currentCountry.toUpperCase()}}`;
            document.getElementById("currentGroup").innerText = `📁 Thể Loại: ${{ch.group || 'General'}}`;
            document.getElementById("currentRes").innerText = `⚡ Độ phân giải: ${{ch.resolution || 'HD'}}`;

            const video = document.getElementById("videoPlayer");
            const overlay = document.getElementById("playerOverlay");
            const overlayText = document.getElementById("overlayText");

            overlay.classList.remove("hidden");
            overlayText.innerText = `Đang kết nối luồng: ${{ch.title}}...`;

            if (Hls.isSupported()) {{
                if (hlsInstance) {{
                    hlsInstance.destroy();
                }}
                hlsInstance = new Hls({{
                    enableWorker: true,
                    lowLatencyMode: true,
                    backBufferLength: 90
                }});
                hlsInstance.loadSource(ch.url);
                hlsInstance.attachMedia(video);

                hlsInstance.on(Hls.Events.MANIFEST_PARSED, () => {{
                    overlay.classList.add("hidden");
                    video.play().catch(() => {{}});
                }});

                hlsInstance.on(Hls.Events.ERROR, (event, data) => {{
                    if (data.fatal) {{
                        switch (data.type) {{
                            case Hls.ErrorTypes.NETWORK_ERROR:
                                overlayText.innerText = "Lỗi mạng hoặc luồng bị gián đoạn. Đang thử lại...";
                                hlsInstance.startLoad();
                                break;
                            case Hls.ErrorTypes.MEDIA_ERROR:
                                overlayText.innerText = "Đang khôi phục giải mã phương tiện...";
                                hlsInstance.recoverMediaError();
                                break;
                            default:
                                overlayText.innerText = "Không thể phát kênh này. Vui lòng chọn kênh khác.";
                                break;
                        }}
                    }}
                }});
            }} else if (video.canPlayType("application/vnd.apple.mpegurl")) {{
                // Native Safari / iOS HLS
                video.src = ch.url;
                video.addEventListener("loadedmetadata", () => {{
                    overlay.classList.add("hidden");
                    video.play();
                }});
            }} else {{
                overlayText.innerText = "Trình duyệt không hỗ trợ phát HLS trực tiếp.";
            }}
        }}

        function reloadStream() {{
            if (activeChannel) {{
                playChannel(activeChannel);
            }}
        }}

        function copyManifestUrl() {{
            navigator.clipboard.writeText(MANIFEST_URL).then(() => {{
                showToast("Đã sao chép liên kết Manifest vào bộ nhớ tạm!");
            }});
        }}

        function showToast(msg) {{
            const toast = document.getElementById("toast");
            document.getElementById("toastMsg").innerText = msg;
            toast.classList.add("show");
            setTimeout(() => {{
                toast.classList.remove("show");
            }}, 3000);
        }}
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)
