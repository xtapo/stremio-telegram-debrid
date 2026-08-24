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

logger = logging.getLogger("tvrun")

tvrun_router = APIRouter(prefix="", tags=["tvrun"])

# ------------------------------------------------------------------
# Cache & Memory Management
# ------------------------------------------------------------------
_tvrun_cache: Dict[str, Tuple[Any, float]] = {}
_tvrun_channels_by_id: Dict[str, Dict[str, Any]] = {}

COUNTRY_CACHE_TTL = 86400  # 24 hours
PLAYLIST_CACHE_TTL = 43200  # 12 hours
GLOBAL_LIST_TTL = 21600  # 6 hours

# ------------------------------------------------------------------
# Popular Countries with Flag & Name mapping
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

SPECIAL_GENRES = [
    "🌐 Free-TV Global [FREETV]",
    "🔴 YouTube Live TV [YT]",
    "⭐ TVRun Verified [FEATURED]",
]

GENRE_OPTIONS = SPECIAL_GENRES + [f"{c['flag']} {c['name']} [{c['code']}]" for c in POPULAR_COUNTRIES]

_country_code_lookup: Dict[str, str] = {}
for c in POPULAR_COUNTRIES:
    _country_code_lookup[c["code"].upper()] = c["code"].lower()
    _country_code_lookup[c["name"].lower()] = c["code"].lower()
    _country_code_lookup[f"{c['flag']} {c['name']} [{c['code']}]".lower()] = c["code"].lower()

# Hardcoded TVRun Featured Channels (from tvrun.online Sl array)
TVRUN_FEATURED_CHANNELS: List[Dict[str, Any]] = [
    {
        "name": "TvOasis",
        "raw_title": "TvOasis",
        "title": "TvOasis",
        "url": "https://live20.bozztv.com/akamaissh101/ssh101/oasistv123/playlist.m3u8",
        "logo": "https://i.imgur.com/qS7ZVXl.png",
        "group": "General;News;Sports;Entertainment;Religious",
        "country": "VE",
        "country_name": "Venezuela",
        "resolution": "1080p Full HD",
        "is_geoblocked": False,
        "description": "Canal que transmite esperanza, fe, información, deportes y entretenimiento desde Trujillo, Venezuela",
        "website": "https://ssh101.com/securelive/index.php?id=oasistv123",
        "id": "tvrun:featured:tvoasis",
        "source": "tvrun_featured"
    }
]

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
            timeout=httpx.Timeout(12.0, connect=6.0),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=60, max_connections=150),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "https://tvrun.online/",
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


def parse_genre_or_country(genre_or_name: Optional[str]) -> Tuple[str, str]:
    """
    Resolve (mode, code/key) from Stremio genre filter or query.
    mode can be 'country', 'freetv', 'youtube', 'featured'.
    """
    if not genre_or_name:
        return ("country", "vn")

    cleaned = genre_or_name.strip()
    low = cleaned.lower()

    if "freetv" in low or "free-tv" in low:
        return ("freetv", "freetv")
    if "youtube" in low or "[yt]" in low:
        return ("youtube", "youtube")
    if "featured" in low or "tvoasis" in low or "tvrun verified" in low:
        return ("featured", "featured")

    m = re.search(r"\[([A-Za-z]{2})\]", cleaned)
    if m:
        return ("country", m.group(1).lower())

    if len(cleaned) == 2 and cleaned.isalpha():
        return ("country", cleaned.lower())

    if low in _country_code_lookup:
        return ("country", _country_code_lookup[low])

    for code, mapped in _country_code_lookup.items():
        if code in low or low in code:
            return ("country", mapped)

    return ("country", "vn")


# ------------------------------------------------------------------
# Fetch & Parse M3U Playlists
# ------------------------------------------------------------------
def parse_m3u_content(content: str, default_country: str = "GLOBAL", prefix: str = "tvrun") -> List[Dict[str, Any]]:
    """Parse M3U string into structured TVRun channel metadata list."""
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
            tvg_country_m = re.search(r'tvg-country="([^"]*)"', line)
            group_m = re.search(r'group-title="([^"]*)"', line)

            parts = line.split(",", 1)
            raw_title = parts[1].strip() if len(parts) > 1 else "TV Channel"

            resolution = "HD"
            if any(k in raw_title for k in ["1080p", "1080i", "FHD", "Full HD"]):
                resolution = "1080p Full HD"
            elif any(k in raw_title for k in ["720p", "HD"]):
                resolution = "720p HD"
            elif any(k in raw_title for k in ["4K", "2160p", "UHD"]):
                resolution = "4K Ultra HD"
            elif any(k in raw_title for k in ["576p", "480p", "SD"]):
                resolution = "SD"

            is_geoblocked = "[Geo-blocked]" in raw_title or "[geo-blocked]" in raw_title

            tvg_id = tvg_id_m.group(1) if tvg_id_m else ""
            tvg_name = tvg_name_m.group(1) if tvg_name_m else ""
            logo = tvg_logo_m.group(1) if tvg_logo_m else ""
            country_val = tvg_country_m.group(1).upper() if tvg_country_m else default_country.upper()
            group = group_m.group(1) if group_m else "General"
            if not group or group == "Undefined":
                group = "General"

            curr["raw_title"] = raw_title
            clean_title = raw_title.replace("[Geo-blocked]", "").replace("[Not 24/7]", "").strip()
            curr["title"] = clean_title or raw_title
            curr["name"] = curr["title"]
            curr["tvg_id"] = tvg_id
            curr["tvg_name"] = tvg_name
            curr["logo"] = logo or "https://tvrun.online/social-preview.png"
            curr["group"] = group
            curr["country"] = country_val
            curr["resolution"] = resolution
            curr["is_geoblocked"] = is_geoblocked

        elif curr is not None and not line.startswith("#"):
            stream_url = line
            curr["url"] = stream_url

            raw_ident = curr.get("tvg_id") or curr.get("title") or f"channel_{len(channels)}"
            slug = re.sub(r"[^a-zA-Z0-9]", "_", raw_ident).strip("_").lower()
            if not slug:
                slug = f"ch_{len(channels)}"
            channel_id = f"{prefix}:{default_country.lower()}:{slug}"
            curr["id"] = channel_id
            curr["source"] = prefix

            _tvrun_channels_by_id[channel_id] = curr
            channels.append(curr)
            curr = None

    return channels


async def fetch_tvrun_country_channels(country_code: str) -> List[Dict[str, Any]]:
    """Fetch M3U playlist for a country from iptv-org/tvrun sources with caching."""
    code = (country_code or "vn").lower()
    cache_key = f"country:{code}"
    now = time.time()

    if cache_key in _tvrun_cache:
        data, exp = _tvrun_cache[cache_key]
        if now < exp:
            return data

    cache_dir = os.path.join("temp_cache", "tvrun")
    os.makedirs(cache_dir, exist_ok=True)
    disk_file = os.path.join(cache_dir, f"country_{code}.json")

    client = get_http_client()
    urls = [
        f"https://raw.githubusercontent.com/iptv-org/iptv/master/streams/{code}.m3u",
        f"https://iptv-org.github.io/iptv/countries/{code}.m3u",
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
        channels = parse_m3u_content(content, default_country=code.upper(), prefix="tvrun")
        if channels:
            _tvrun_cache[cache_key] = (channels, now + PLAYLIST_CACHE_TTL)
            try:
                with open(disk_file, "w", encoding="utf-8") as f:
                    json.dump(channels, f, ensure_ascii=False)
            except Exception:
                pass
            return channels

    if os.path.exists(disk_file):
        try:
            with open(disk_file, "r", encoding="utf-8") as f:
                channels = json.load(f)
                for ch in channels:
                    _tvrun_channels_by_id[ch["id"]] = ch
                _tvrun_cache[cache_key] = (channels, now + 3600)
                return channels
        except Exception as e:
            logger.warning(f"Failed loading disk cache for country_{code}: {e}")

    return []


async def fetch_freetv_channels() -> List[Dict[str, Any]]:
    """Fetch Free-TV 2,000+ Global Channels (tvrun.online source)."""
    cache_key = "freetv_global"
    now = time.time()

    if cache_key in _tvrun_cache:
        data, exp = _tvrun_cache[cache_key]
        if now < exp:
            return data

    cache_dir = os.path.join("temp_cache", "tvrun")
    os.makedirs(cache_dir, exist_ok=True)
    disk_file = os.path.join(cache_dir, "freetv_global.json")

    client = get_http_client()
    url = "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8"

    try:
        r = await client.get(url)
        if r.status_code == 200 and r.text and "#EXTM3U" in r.text:
            channels = parse_m3u_content(r.text, default_country="FREETV", prefix="tvrun:freetv")
            if channels:
                _tvrun_cache[cache_key] = (channels, now + GLOBAL_LIST_TTL)
                try:
                    with open(disk_file, "w", encoding="utf-8") as f:
                        json.dump(channels, f, ensure_ascii=False)
                except Exception:
                    pass
                return channels
    except Exception as e:
        logger.warning(f"Failed fetching Free-TV playlist: {e}")

    if os.path.exists(disk_file):
        try:
            with open(disk_file, "r", encoding="utf-8") as f:
                channels = json.load(f)
                for ch in channels:
                    _tvrun_channels_by_id[ch["id"]] = ch
                _tvrun_cache[cache_key] = (channels, now + 3600)
                return channels
        except Exception as e:
            logger.warning(f"Failed loading Free-TV disk cache: {e}")

    return []


async def fetch_youtube_live_channels() -> List[Dict[str, Any]]:
    """Fetch YouTube Live global stream channels (tvrun.online source)."""
    cache_key = "youtube_live"
    now = time.time()

    if cache_key in _tvrun_cache:
        data, exp = _tvrun_cache[cache_key]
        if now < exp:
            return data

    cache_dir = os.path.join("temp_cache", "tvrun")
    os.makedirs(cache_dir, exist_ok=True)
    disk_file = os.path.join(cache_dir, "youtube_live.json")

    client = get_http_client()
    urls = [
        "https://raw.githubusercontent.com/benmoose39/YouTube_to_m3u/main/youtube.m3u",
        "https://live-iptv.github.io/youtube_live/youtube.m3u",
        "https://live-iptv.github.io/youtube_live/malayalam.m3u",
        "https://live-iptv.github.io/youtube_live/tamil.m3u",
    ]

    all_channels: List[Dict[str, Any]] = []
    seen_urls = set()

    for u in urls:
        try:
            r = await client.get(u)
            if r.status_code == 200 and r.text and "#EXTM3U" in r.text:
                parsed = parse_m3u_content(r.text, default_country="YT", prefix="tvrun:yt")
                for ch in parsed:
                    if ch["url"] not in seen_urls:
                        seen_urls.add(ch["url"])
                        all_channels.append(ch)
        except Exception as e:
            logger.debug(f"Failed fetching YouTube M3U {u}: {e}")

    if all_channels:
        _tvrun_cache[cache_key] = (all_channels, now + GLOBAL_LIST_TTL)
        try:
            with open(disk_file, "w", encoding="utf-8") as f:
                json.dump(all_channels, f, ensure_ascii=False)
        except Exception:
            pass
        return all_channels

    if os.path.exists(disk_file):
        try:
            with open(disk_file, "r", encoding="utf-8") as f:
                channels = json.load(f)
                for ch in channels:
                    _tvrun_channels_by_id[ch["id"]] = ch
                _tvrun_cache[cache_key] = (channels, now + 3600)
                return channels
        except Exception as e:
            logger.warning(f"Failed loading YouTube Live disk cache: {e}")

    return []


def get_featured_channels() -> List[Dict[str, Any]]:
    """Return TVRun verified and exclusive channels."""
    for ch in TVRUN_FEATURED_CHANNELS:
        _tvrun_channels_by_id[ch["id"]] = ch
    return TVRUN_FEATURED_CHANNELS


async def fetch_channels_by_mode(mode: str, code_or_key: str) -> List[Dict[str, Any]]:
    """Dispatch fetch request according to mode."""
    if mode == "freetv":
        return await fetch_freetv_channels()
    elif mode == "youtube":
        return await fetch_youtube_live_channels()
    elif mode == "featured":
        return get_featured_channels()
    else:
        return await fetch_tvrun_country_channels(code_or_key)


async def fetch_all_countries_list() -> List[Dict[str, Any]]:
    """Fetch complete list of 200+ countries with caching."""
    cache_key = "all_countries"
    now = time.time()

    if cache_key in _tvrun_cache:
        data, exp = _tvrun_cache[cache_key]
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
                _tvrun_cache[cache_key] = (countries, now + COUNTRY_CACHE_TTL)
                return countries
    except Exception as e:
        logger.warning(f"Failed fetching all countries from {url}: {e}")

    return POPULAR_COUNTRIES


# ------------------------------------------------------------------
# HLS Stream Proxy with M3U8 Rewriting & CORS bypass
# ------------------------------------------------------------------
def rewrite_m3u8_playlist(content: str, base_url: str, referer: Optional[str], proxy_endpoint: str) -> str:
    """Rewrite relative and absolute URLs in m3u8 playlist to route through stream_proxy."""
    lines = content.splitlines()
    rewritten_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("#"):
            if 'URI="' in stripped:
                def replace_uri(match):
                    uri = match.group(1)
                    abs_uri = urllib.parse.urljoin(base_url, uri)
                    proxy_uri = f"{proxy_endpoint}?url={urllib.parse.quote(abs_uri, safe='')}"
                    if referer:
                        proxy_uri += f"&referer={urllib.parse.quote(referer, safe='')}"
                    return f'URI="{proxy_uri}"'

                new_line = re.sub(r'URI="([^"]+)"', replace_uri, stripped)
                rewritten_lines.append(new_line)
            else:
                rewritten_lines.append(stripped)
        else:
            abs_url = urllib.parse.urljoin(base_url, stripped)
            proxy_url = f"{proxy_endpoint}?url={urllib.parse.quote(abs_url, safe='')}"
            if referer:
                proxy_url += f"&referer={urllib.parse.quote(referer, safe='')}"
            rewritten_lines.append(proxy_url)

    return "\n".join(rewritten_lines)


@tvrun_router.get("/stream_proxy")
@tvrun_router.get("/tvrun/stream_proxy")
async def tvrun_stream_proxy(
    request: Request,
    url: str = Query(..., description="Target stream or segment URL"),
    referer: Optional[str] = Query(None, description="Optional custom referer")
):
    """Proxy HLS streams & TS segments with CORS headers to play seamlessly in Web Player."""
    if not url:
        raise HTTPException(status_code=400, detail="Missing URL parameter")

    target_url = urllib.parse.unquote(url).strip()
    if " " in target_url:
        target_url = target_url.replace(" ", "+")

    ref = referer or "https://tvrun.online/"
    req_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": ref,
        "Accept": "*/*",
    }

    # Pass Range header if present
    if "range" in request.headers:
        req_headers["Range"] = request.headers["range"]

    base_url = str(request.base_url).rstrip("/")
    proxy_endpoint = f"{base_url}/tvrun/stream_proxy"

    client = get_http_client()
    try:
        upstream_resp = await client.get(target_url, headers=req_headers)
        
        # Check if it's an M3U8 playlist
        content_type = upstream_resp.headers.get("Content-Type", "")
        body_sample = upstream_resp.text[:500] if len(upstream_resp.content) < 2000000 else ""

        if "#EXTM3U" in body_sample or "mpegurl" in content_type or target_url.endswith(".m3u8"):
            rewritten = rewrite_m3u8_playlist(upstream_resp.text, target_url, ref, proxy_endpoint)
            return Response(
                content=rewritten,
                status_code=200,
                media_type="application/vnd.apple.mpegurl",
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                }
            )

        # Video chunk / binary TS segment
        return Response(
            content=upstream_resp.content,
            status_code=upstream_resp.status_code,
            media_type=content_type or "video/mp2t",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                "Access-Control-Allow-Headers": "*",
                "Cache-Control": "public, max-age=3600",
            }
        )
    except Exception as e:
        logger.debug(f"TVRun stream proxy error for {target_url}: {e}")
        return Response(
            content=f"Stream proxy fetch error: {e}",
            status_code=502,
            media_type="text/plain",
            headers={"Access-Control-Allow-Origin": "*"}
        )


# ------------------------------------------------------------------
# Stremio Manifest
# ------------------------------------------------------------------
def get_tvrun_manifest(api_key: str = "") -> Dict[str, Any]:
    show_on_board = getattr(Config, "ENABLE_BOARD_TVRUN", True)
    main_req = not show_on_board

    return {
        "id": "com.stremio.tvrun.online",
        "version": "1.0.0",
        "name": "TVRun - Free Global Live TV Streaming",
        "description": "Xem trực tiếp hàng ngàn kênh truyền hình quốc tế miễn phí từ TVRun (tvrun.online) - Tích hợp 200+ Quốc Gia, Free-TV Global 2.000+ kênh, YouTube Live TV và các luồng phát tốc độ cao.",
        "logo": "https://tvrun.online/social-preview.png",
        "resources": [
            "catalog",
            {
                "name": "meta",
                "types": ["tv"],
                "idPrefixes": ["tvrun:"]
            },
            {
                "name": "stream",
                "types": ["tv"],
                "idPrefixes": ["tvrun:"]
            }
        ],
        "types": ["tv"],
        "catalogs": [
            {
                "type": "tv",
                "id": "tvrun_channels",
                "name": "TVRun - Global Live TV Channels",
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
@tvrun_router.get("/manifest.json")
@tvrun_router.get("/tvrun/manifest.json")
@tvrun_router.get("/{api_key}/tvrun/manifest.json")
async def manifest_endpoint(api_key: str = ""):
    if not getattr(Config, "ENABLE_SOURCE_TVRUN", True):
        raise HTTPException(status_code=404, detail="TVRun Source is disabled")
    return JSONResponse(get_tvrun_manifest(api_key))


# ------------------------------------------------------------------
# Catalog Endpoints
# ------------------------------------------------------------------
@tvrun_router.get("/catalog/{type}/{id}.json")
@tvrun_router.get("/catalog/{type}/{id}/{extra}.json")
@tvrun_router.get("/tvrun/catalog/{type}/{id}.json")
@tvrun_router.get("/tvrun/catalog/{type}/{id}/{extra}.json")
@tvrun_router.get("/{api_key}/tvrun/catalog/{type}/{id}.json")
@tvrun_router.get("/{api_key}/tvrun/catalog/{type}/{id}/{extra}.json")
async def catalog_endpoint(
    type: str,
    id: str,
    extra: Optional[str] = None,
    api_key: str = ""
):
    if not getattr(Config, "ENABLE_SOURCE_TVRUN", True):
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

    mode, code_or_key = parse_genre_or_country(genre_filter)
    channels = await fetch_channels_by_mode(mode, code_or_key)

    metas = []
    tag_label = "Free Global TV" if mode == "freetv" else ("YouTube Live" if mode == "youtube" else ("TVRun Verified" if mode == "featured" else code_or_key.upper()))

    for ch in channels:
        name = ch.get("title") or ch.get("name") or "TV Channel"
        ch_id = ch.get("id") or f"tvrun:{code_or_key}:{name}"
        logo = ch.get("logo") or "https://tvrun.online/social-preview.png"
        group = ch.get("group") or "General"
        resolution = ch.get("resolution") or "HD"
        geoblocked = ch.get("is_geoblocked", False)
        country_display = ch.get("country", tag_label)

        if search_query:
            norm_q = normalize_text(search_query)
            norm_name = normalize_text(name)
            norm_id = normalize_text(ch_id)
            norm_group = normalize_text(group)
            if norm_q not in norm_name and norm_q not in norm_id and norm_q not in norm_group:
                continue

        geo_badge = " [Geo-blocked]" if geoblocked else ""
        desc = (
            f"📺 Kênh: {name}{geo_badge}\n"
            f"🌐 Quốc gia / Nguồn: {country_display}\n"
            f"📁 Thể loại: {group}\n"
            f"⚡ Độ phân giải: {resolution}\n"
            f"📡 Nguồn phát: TVRun Free Global Streaming (tvrun.online)"
        )

        metas.append({
            "id": ch_id,
            "type": "tv",
            "name": f"{name} ({country_display})",
            "poster": logo,
            "background": logo,
            "logo": logo,
            "description": desc,
            "genres": [f"Nguồn: {country_display}", group, "TVRun Live"],
            "posterShape": "square",
        })

    if skip_val > 0 and skip_val < len(metas):
        metas = metas[skip_val:]

    return JSONResponse({"metas": metas})


# ------------------------------------------------------------------
# Meta Endpoints
# ------------------------------------------------------------------
@tvrun_router.get("/meta/{type}/{id}.json")
@tvrun_router.get("/tvrun/meta/{type}/{id}.json")
@tvrun_router.get("/{api_key}/tvrun/meta/{type}/{id}.json")
async def meta_endpoint(type: str, id: str, api_key: str = ""):
    if not getattr(Config, "ENABLE_SOURCE_TVRUN", True):
        raise HTTPException(status_code=404, detail="TVRun is disabled")

    ch = _tvrun_channels_by_id.get(id)
    if not ch:
        parts = id.split(":")
        if len(parts) >= 3:
            section = parts[1]
            if section == "featured":
                get_featured_channels()
            elif section == "freetv":
                await fetch_freetv_channels()
            elif section == "yt":
                await fetch_youtube_live_channels()
            else:
                await fetch_tvrun_country_channels(section)
            ch = _tvrun_channels_by_id.get(id)

    if ch:
        name = ch.get("title") or ch.get("name") or "TV Channel"
        logo = ch.get("logo") or "https://tvrun.online/social-preview.png"
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
                    f"Quốc gia / Phân loại: {country} | Thể loại: {group} | Chuẩn: {resolution}\n"
                    f"Nguồn: TVRun Free Global Streaming (tvrun.online)"
                ),
                "genres": [f"Khu vực: {country}", group, "Live TV"],
                "posterShape": "square"
            }
        })

    return JSONResponse({
        "meta": {
            "id": id,
            "type": "tv",
            "name": f"TV Channel {id}",
            "poster": "https://tvrun.online/social-preview.png",
            "description": "Kênh truyền hình trực tiếp TVRun",
            "genres": ["Live TV", "TVRun"]
        }
    })


# ------------------------------------------------------------------
# Stream Endpoints
# ------------------------------------------------------------------
@tvrun_router.get("/stream/{type}/{id}.json")
@tvrun_router.get("/tvrun/stream/{type}/{id}.json")
@tvrun_router.get("/{api_key}/tvrun/stream/{type}/{id}.json")
async def stream_endpoint(request: Request, type: str, id: str, api_key: str = ""):
    if not getattr(Config, "ENABLE_SOURCE_TVRUN", True):
        return JSONResponse({"streams": []})

    ch = _tvrun_channels_by_id.get(id)
    if not ch:
        parts = id.split(":")
        if len(parts) >= 3:
            section = parts[1]
            if section == "featured":
                get_featured_channels()
            elif section == "freetv":
                await fetch_freetv_channels()
            elif section == "yt":
                await fetch_youtube_live_channels()
            else:
                await fetch_tvrun_country_channels(section)
            ch = _tvrun_channels_by_id.get(id)

    if not ch or not ch.get("url"):
        return JSONResponse({"streams": []})

    stream_url = ch["url"]
    name = ch.get("title") or ch.get("name") or "TV Channel"
    resolution = ch.get("resolution") or "Live HLS"
    country = ch.get("country") or "Global"

    base_url = str(request.base_url).rstrip("/")
    proxy_url = f"{base_url}/tvrun/stream_proxy?url={urllib.parse.quote(stream_url, safe='')}&referer={urllib.parse.quote('https://tvrun.online/', safe='')}"

    streams = [
        {
            "name": f"TVRun [{country}] • {resolution}",
            "title": f"⚡ {name}\n[Luồng Trực Tiếp HLS • Nguồn TVRun • {resolution}]",
            "url": stream_url,
            "behaviorHints": {
                "notWebReady": False,
                "proxyHeaders": {
                    "request": {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Referer": "https://tvrun.online/"
                    }
                }
            }
        },
        {
            "name": f"TVRun [Proxy Fast] • {resolution}",
            "title": f"🚀 {name} (Proxy Dự Phòng)\n[Luồng Proxy Chống Chặn • Tốc Độ Cao]",
            "url": proxy_url
        }
    ]

    return JSONResponse({"streams": streams})


# ------------------------------------------------------------------
# M3U Playlist Export
# ------------------------------------------------------------------
@tvrun_router.get("/playlist.m3u")
@tvrun_router.get("/tvrun/playlist.m3u")
async def export_m3u_playlist(
    country: Optional[str] = None,
    source: Optional[str] = None,
    group: Optional[str] = None
):
    """Export M3U playlist format for external IPTV players (VLC, TiviMate, OTT Navigator)."""
    channels: List[Dict[str, Any]] = []

    if source == "freetv":
        channels = await fetch_freetv_channels()
    elif source == "youtube" or source == "yt":
        channels = await fetch_youtube_live_channels()
    elif source == "featured":
        channels = get_featured_channels()
    elif country:
        channels = await fetch_tvrun_country_channels(country)
    else:
        # Default combination: Featured + VN + Top Countries
        channels.extend(get_featured_channels())
        channels.extend(await fetch_tvrun_country_channels("vn"))
        channels.extend(await fetch_tvrun_country_channels("us"))

    if group:
        g_low = group.lower()
        channels = [c for c in channels if g_low in (c.get("group") or "").lower()]

    lines = ["#EXTM3U"]
    for c in channels:
        tvg_id = c.get("tvg_id", "")
        tvg_logo = c.get("logo", "")
        group_title = c.get("group", "General")
        name = c.get("title") or c.get("name") or "TV Channel"
        url = c.get("url", "")
        if not url:
            continue
        lines.append(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{tvg_logo}" group-title="{group_title}",{name}')
        lines.append(url)

    m3u_data = "\n".join(lines)
    return Response(
        content=m3u_data,
        media_type="application/x-mpegurl",
        headers={"Content-Disposition": "attachment; filename=tvrun_playlist.m3u"}
    )


# ------------------------------------------------------------------
# JSON APIs for Web TV Player
# ------------------------------------------------------------------
@tvrun_router.get("/api/countries")
@tvrun_router.get("/tvrun/api/countries")
async def api_countries():
    countries = await fetch_all_countries_list()
    return JSONResponse({
        "popular": POPULAR_COUNTRIES,
        "special": [
            {"id": "vn", "name": "Việt Nam", "flag": "🇻🇳", "type": "country"},
            {"id": "us", "name": "United States", "flag": "🇺🇸", "type": "country"},
            {"id": "uk", "name": "United Kingdom", "flag": "🇬🇧", "type": "country"},
            {"id": "jp", "name": "Nhật Bản", "flag": "🇯🇵", "type": "country"},
            {"id": "kr", "name": "Hàn Quốc", "flag": "🇰🇷", "type": "country"},
            {"id": "freetv", "name": "Free-TV Global (2,000+)", "flag": "🌐", "type": "special"},
            {"id": "youtube", "name": "YouTube Live TV", "flag": "🔴", "type": "special"},
            {"id": "featured", "name": "TVRun Verified", "flag": "⭐", "type": "special"},
        ],
        "countries": countries
    })


@tvrun_router.get("/api/channels")
@tvrun_router.get("/tvrun/api/channels")
async def api_channels(
    source: str = Query("vn", description="Source code: ISO 2-letter, freetv, youtube, featured")
):
    s_low = source.lower()
    if s_low == "freetv":
        channels = await fetch_freetv_channels()
    elif s_low in ["youtube", "yt"]:
        channels = await fetch_youtube_live_channels()
    elif s_low == "featured":
        channels = get_featured_channels()
    else:
        channels = await fetch_tvrun_country_channels(s_low)

    return JSONResponse({
        "source": s_low,
        "total": len(channels),
        "channels": channels
    })


# ------------------------------------------------------------------
# Web TV Player UI (/tvrun/tv, /tvrun/player, /tvrun)
# ------------------------------------------------------------------
@tvrun_router.get("", response_class=HTMLResponse)
@tvrun_router.get("/", response_class=HTMLResponse)
@tvrun_router.get("/tv", response_class=HTMLResponse)
@tvrun_router.get("/player", response_class=HTMLResponse)
@tvrun_router.get("/tvrun/tv", response_class=HTMLResponse)
@tvrun_router.get("/tvrun/player", response_class=HTMLResponse)
@tvrun_router.get("/tvrun", response_class=HTMLResponse)
async def web_tv_player_page(request: Request, source: Optional[str] = "vn", ch: Optional[str] = None):
    """Modern Dark Mode Glassmorphism Web TV Player for TVRun Free Global TV Streaming."""
    host = request.headers.get("host") or f"127.0.0.1:{Config.PORT}"
    scheme = request.url.scheme
    manifest_url = f"{scheme}://{host}/tvrun/manifest.json"
    stremio_link = manifest_url.replace("http://", "stremio://").replace("https://", "stremio://")
    playlist_m3u_url = f"{scheme}://{host}/tvrun/playlist.m3u"

    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TVRun - Free Global TV Streaming | Xem Kênh TV Trực Tuyến Toàn Cầu</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <style>
        :root {{
            --bg-primary: #070913;
            --bg-secondary: #0d1224;
            --bg-glass: rgba(18, 24, 45, 0.85);
            --bg-glass-card: rgba(26, 35, 64, 0.6);
            --accent: #ff4785;
            --accent-gradient: linear-gradient(135deg, #ff4785 0%, #7928ca 100%);
            --accent-hover: linear-gradient(135deg, #ff5e98 0%, #8b3cd9 100%);
            --cyan-glow: #00f2fe;
            --emerald: #10b981;
            --amber: #f59e0b;
            --rose: #f43f5e;
            --text-primary: #f8fafc;
            --text-muted: #94a3b8;
            --border-glass: rgba(255, 255, 255, 0.08);
            --border-highlight: rgba(255, 71, 133, 0.4);
            --sidebar-w: 420px;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Outfit', sans-serif;
            -webkit-tap-highlight-color: transparent;
        }}

        body {{
            background-color: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
            background-image: 
                radial-gradient(circle at 15% 15%, rgba(255, 71, 133, 0.14) 0%, transparent 40%),
                radial-gradient(circle at 85% 80%, rgba(121, 40, 202, 0.16) 0%, transparent 45%);
        }}

        header {{
            height: 72px;
            background: var(--bg-glass);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border-bottom: 1px solid var(--border-glass);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 28px;
            position: sticky;
            top: 0;
            z-index: 100;
        }}

        .logo-area {{
            display: flex;
            align-items: center;
            gap: 14px;
            text-decoration: none;
            color: inherit;
        }}

        .logo-icon {{
            width: 44px;
            height: 44px;
            border-radius: 12px;
            background: var(--accent-gradient);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
            color: #fff;
            box-shadow: 0 0 20px rgba(255, 71, 133, 0.4);
        }}

        .logo-text h1 {{
            font-size: 20px;
            font-weight: 800;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #ffffff 30%, #ff7ab0 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .logo-text p {{
            font-size: 11px;
            color: var(--text-muted);
            font-weight: 500;
        }}

        .header-actions {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 9px 18px;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 600;
            text-decoration: none;
            cursor: pointer;
            transition: all 0.25s ease;
            border: none;
        }}

        .btn-stremio {{
            background: var(--accent-gradient);
            color: #fff;
            box-shadow: 0 4px 14px rgba(255, 71, 133, 0.35);
        }}

        .btn-stremio:hover {{
            background: var(--accent-hover);
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(255, 71, 133, 0.5);
        }}

        .btn-ghost {{
            background: var(--bg-glass-card);
            color: var(--text-primary);
            border: 1px solid var(--border-glass);
        }}

        .btn-ghost:hover {{
            background: rgba(255, 255, 255, 0.12);
            border-color: rgba(255, 255, 255, 0.2);
        }}

        .main-layout {{
            display: flex;
            flex: 1;
            height: calc(100vh - 72px);
            position: relative;
        }}

        .player-container {{
            flex: 1;
            display: flex;
            flex-direction: column;
            background: #000;
            position: relative;
        }}

        .video-wrapper {{
            flex: 1;
            position: relative;
            background: #000;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }}

        video {{
            width: 100%;
            height: 100%;
            max-height: calc(100vh - 160px);
            object-fit: contain;
            background: #000;
        }}

        .player-overlay {{
            position: absolute;
            inset: 0;
            background: rgba(7, 9, 19, 0.85);
            backdrop-filter: blur(8px);
            display: none;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 16px;
            z-index: 10;
            padding: 24px;
            text-align: center;
        }}

        .player-overlay.show {{
            display: flex;
        }}

        .overlay-icon {{
            font-size: 48px;
            color: var(--rose);
            margin-bottom: 8px;
        }}

        .overlay-title {{
            font-size: 18px;
            font-weight: 700;
            color: #fff;
        }}

        .overlay-desc {{
            font-size: 13px;
            color: var(--text-muted);
            max-width: 480px;
            line-height: 1.5;
        }}

        .overlay-actions {{
            display: flex;
            gap: 12px;
            margin-top: 8px;
        }}

        .player-bar {{
            height: 88px;
            background: var(--bg-secondary);
            border-top: 1px solid var(--border-glass);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 28px;
        }}

        .channel-info {{
            display: flex;
            align-items: center;
            gap: 16px;
        }}

        .channel-avatar {{
            width: 52px;
            height: 52px;
            border-radius: 12px;
            background: #1e293b;
            object-fit: contain;
            padding: 6px;
            border: 1px solid var(--border-glass);
        }}

        .channel-meta h2 {{
            font-size: 17px;
            font-weight: 700;
            margin-bottom: 4px;
        }}

        .channel-meta .badges {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}

        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-size: 11px;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.08);
            color: var(--text-muted);
        }}

        .badge.live {{
            background: rgba(16, 185, 129, 0.15);
            color: var(--emerald);
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}

        .badge.quality {{
            background: rgba(255, 71, 133, 0.15);
            color: #ff7ab0;
            border: 1px solid rgba(255, 71, 133, 0.3);
        }}

        .sidebar {{
            width: var(--sidebar-w);
            background: var(--bg-secondary);
            border-left: 1px solid var(--border-glass);
            display: flex;
            flex-direction: column;
            height: 100%;
        }}

        .sidebar-header {{
            padding: 16px;
            border-bottom: 1px solid var(--border-glass);
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}

        .pill-tabs {{
            display: flex;
            gap: 6px;
            overflow-x: auto;
            padding-bottom: 4px;
        }}

        .pill-tabs::-webkit-scrollbar {{
            height: 3px;
        }}

        .pill-tabs::-webkit-scrollbar-thumb {{
            background: rgba(255, 255, 255, 0.2);
            border-radius: 3px;
        }}

        .pill-btn {{
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            background: var(--bg-glass-card);
            color: var(--text-muted);
            border: 1px solid var(--border-glass);
            cursor: pointer;
            white-space: nowrap;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s;
        }}

        .pill-btn:hover, .pill-btn.active {{
            background: var(--accent-gradient);
            color: #fff;
            border-color: transparent;
            box-shadow: 0 2px 10px rgba(255, 71, 133, 0.3);
        }}

        .search-box {{
            position: relative;
        }}

        .search-box input {{
            width: 100%;
            padding: 10px 14px 10px 38px;
            border-radius: 10px;
            background: var(--bg-glass-card);
            border: 1px solid var(--border-glass);
            color: #fff;
            font-size: 13px;
            outline: none;
            transition: border-color 0.2s;
        }}

        .search-box input:focus {{
            border-color: var(--accent);
        }}

        .search-box i {{
            position: absolute;
            left: 14px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
            font-size: 13px;
        }}

        .filter-row {{
            display: flex;
            gap: 8px;
        }}

        .select-filter {{
            flex: 1;
            padding: 8px 12px;
            border-radius: 8px;
            background: var(--bg-glass-card);
            border: 1px solid var(--border-glass);
            color: var(--text-primary);
            font-size: 12px;
            outline: none;
            cursor: pointer;
        }}

        .select-filter option {{
            background: var(--bg-secondary);
            color: #fff;
        }}

        .channel-list {{
            flex: 1;
            overflow-y: auto;
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        .channel-item {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 12px;
            border-radius: 10px;
            background: var(--bg-glass-card);
            border: 1px solid var(--border-glass);
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .channel-item:hover {{
            background: rgba(255, 255, 255, 0.08);
            border-color: rgba(255, 255, 255, 0.2);
            transform: translateX(2px);
        }}

        .channel-item.active {{
            background: rgba(255, 71, 133, 0.15);
            border-color: var(--border-highlight);
            box-shadow: 0 0 16px rgba(255, 71, 133, 0.2);
        }}

        .channel-item img {{
            width: 40px;
            height: 40px;
            border-radius: 8px;
            object-fit: contain;
            background: #0f172a;
            padding: 4px;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }}

        .channel-item-info {{
            flex: 1;
            min-width: 0;
        }}

        .channel-item-title {{
            font-size: 13px;
            font-weight: 600;
            color: #fff;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .channel-item-desc {{
            font-size: 11px;
            color: var(--text-muted);
            display: flex;
            gap: 6px;
            margin-top: 2px;
        }}

        .status-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--emerald);
            box-shadow: 0 0 8px var(--emerald);
        }}

        .loading-spinner {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 40px 0;
            color: var(--text-muted);
            gap: 12px;
        }}

        .loading-spinner i {{
            font-size: 28px;
            color: var(--accent);
        }}

        @media (max-width: 992px) {{
            .main-layout {{
                flex-direction: column;
                height: auto;
            }}
            .player-container {{
                height: 55vw;
                min-height: 280px;
            }}
            .sidebar {{
                width: 100%;
                height: 500px;
            }}
        }}
    </style>
</head>
<body>

    <header>
        <a href="/tvrun/tv" class="logo-area">
            <div class="logo-icon">
                <i class="fa-solid fa-satellite-dish"></i>
            </div>
            <div class="logo-text">
                <h1>TVRUN ONLINE</h1>
                <p>Free Global Live TV Streaming</p>
            </div>
        </a>

        <div class="header-actions">
            <a href="{playlist_m3u_url}" class="btn btn-ghost" title="Tải M3U Playlist cho VLC / TiviMate">
                <i class="fa-solid fa-file-arrow-down"></i>
                <span>Tải M3U</span>
            </a>
            <a href="{stremio_link}" class="btn btn-stremio">
                <i class="fa-solid fa-circle-play"></i>
                <span>Cài Đặt Stremio</span>
            </a>
        </div>
    </header>

    <div class="main-layout">
        <!-- Player Area -->
        <div class="player-container">
            <div class="video-wrapper">
                <video id="videoPlayer" controls autoplay playsinline></video>
                <div id="playerOverlay" class="player-overlay">
                    <i class="fa-solid fa-triangle-exclamation overlay-icon"></i>
                    <div class="overlay-title" id="overlayTitle">Luồng Phát Tạm Thời Gián Đoạn</div>
                    <div class="overlay-desc" id="overlayDesc">Kênh này có thể đang bảo trì, bị chặn địa lý hoặc giới hạn CORS trình duyệt. Bạn có thể thử kết nối qua proxy hoặc chuyển kênh khác.</div>
                    <div class="overlay-actions">
                        <button class="btn btn-stremio" onclick="retryWithProxy()">
                            <i class="fa-solid fa-bolt"></i>
                            <span>Phát Qua Proxy</span>
                        </button>
                        <button class="btn btn-ghost" onclick="playNextChannel()">
                            <i class="fa-solid fa-forward"></i>
                            <span>Kênh Kế Tiếp</span>
                        </button>
                    </div>
                </div>
            </div>
            <div class="player-bar">
                <div class="channel-info">
                    <img id="currentLogo" class="channel-avatar" src="https://tvrun.online/social-preview.png" alt="Channel Logo">
                    <div class="channel-meta">
                        <h2 id="currentTitle">Đang Tải Danh Sách Kênh...</h2>
                        <div class="badges">
                            <span class="badge live"><span class="status-dot"></span> LIVE</span>
                            <span id="currentGroup" class="badge">General</span>
                            <span id="currentCountry" class="badge">GLOBAL</span>
                            <span id="currentRes" class="badge quality">1080p FHD</span>
                        </div>
                    </div>
                </div>
                <div class="header-actions">
                    <button class="btn btn-ghost" onclick="copyStreamUrl()" title="Sao chép Link Stream">
                        <i class="fa-regular fa-copy"></i>
                        <span>Copy Stream</span>
                    </button>
                </div>
            </div>
        </div>

        <!-- Sidebar Navigation -->
        <div class="sidebar">
            <div class="sidebar-header">
                <div class="pill-tabs" id="quickPills">
                    <button class="pill-btn active" data-src="vn">🇻🇳 Việt Nam</button>
                    <button class="pill-btn" data-src="freetv">🌐 Free-TV Global</button>
                    <button class="pill-btn" data-src="youtube">🔴 YouTube Live</button>
                    <button class="pill-btn" data-src="us">🇺🇸 Mỹ (US)</button>
                    <button class="pill-btn" data-src="uk">🇬🇧 Anh (UK)</button>
                    <button class="pill-btn" data-src="jp">🇯🇵 Nhật Bản</button>
                    <button class="pill-btn" data-src="kr">🇰🇷 Hàn Quốc</button>
                    <button class="pill-btn" data-src="featured">⭐ TVRun Verified</button>
                </div>

                <div class="search-box">
                    <i class="fa-solid fa-magnifying-glass"></i>
                    <input type="text" id="searchInput" placeholder="Tìm kiếm kênh TV, tin tức, thể thao...">
                </div>

                <div class="filter-row">
                    <select id="countrySelect" class="select-filter">
                        <option value="vn">🇻🇳 Việt Nam (VN)</option>
                        <option value="freetv">🌐 Free-TV 2,000+ Kênh</option>
                        <option value="youtube">🔴 YouTube Live TV</option>
                        <option value="us">🇺🇸 United States (US)</option>
                        <option value="uk">🇬🇧 United Kingdom (UK)</option>
                        <option value="jp">🇯🇵 Nhật Bản (JP)</option>
                        <option value="kr">🇰🇷 Hàn Quốc (KR)</option>
                        <option value="fr">🇫🇷 Pháp (FR)</option>
                        <option value="de">🇩🇪 Đức (DE)</option>
                        <option value="cn">🇨🇳 Trung Quốc (CN)</option>
                        <option value="in">🇮🇳 Ấn Độ (IN)</option>
                        <option value="featured">⭐ TVRun Verified</option>
                    </select>

                    <select id="categorySelect" class="select-filter">
                        <option value="ALL">Tất cả thể loại</option>
                    </select>
                </div>
            </div>

            <div class="channel-list" id="channelList">
                <div class="loading-spinner">
                    <i class="fa-solid fa-circle-notch fa-spin"></i>
                    <span>Đang tải danh sách kênh...</span>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentSource = "{source or 'vn'}";
        let allChannels = [];
        let filteredChannels = [];
        let activeChannel = null;
        let activeIndex = 0;
        let isUsingProxy = false;
        let hls = null;

        const videoEl = document.getElementById("videoPlayer");
        const playerOverlay = document.getElementById("playerOverlay");
        const channelListEl = document.getElementById("channelList");
        const searchInput = document.getElementById("searchInput");
        const countrySelect = document.getElementById("countrySelect");
        const categorySelect = document.getElementById("categorySelect");

        async function init() {{
            setupEventListeners();
            await loadCountries();
            await loadChannels(currentSource);
        }}

        function setupEventListeners() {{
            document.querySelectorAll("#quickPills .pill-btn").forEach(btn => {{
                btn.addEventListener("click", () => {{
                    document.querySelectorAll("#quickPills .pill-btn").forEach(b => b.classList.remove("active"));
                    btn.classList.add("active");
                    const src = btn.dataset.src;
                    countrySelect.value = src;
                    loadChannels(src);
                }});
            }});

            countrySelect.addEventListener("change", (e) => {{
                const src = e.target.value;
                document.querySelectorAll("#quickPills .pill-btn").forEach(b => {{
                    b.classList.toggle("active", b.dataset.src === src);
                }});
                loadChannels(src);
            }});

            categorySelect.addEventListener("change", () => filterAndRenderChannels());
            searchInput.addEventListener("input", () => filterAndRenderChannels());
        }}

        async function loadCountries() {{
            try {{
                const res = await fetch("/tvrun/api/countries");
                if (res.ok) {{
                    const data = await res.json();
                    if (data.countries && data.countries.length > 0) {{
                        const opts = [];
                        opts.push('<optgroup label="Nguồn Đặc Biệt">');
                        opts.push('<option value="vn">🇻🇳 Việt Nam (VN)</option>');
                        opts.push('<option value="freetv">🌐 Free-TV Global (2,000+ Kênh)</option>');
                        opts.push('<option value="youtube">🔴 YouTube Live Streams</option>');
                        opts.push('<option value="featured">⭐ TVRun Verified / TvOasis</option>');
                        opts.push('</optgroup>');

                        opts.push('<optgroup label="200+ Quốc Gia">');
                        data.countries.forEach(c => {{
                            const flag = c.flag || "🌐";
                            opts.push(`<option value="${{c.code.toLowerCase()}}">${{flag}} ${{c.name}} (${{c.code}})</option>`);
                        }});
                        opts.push('</optgroup>');
                        countrySelect.innerHTML = opts.join('');
                        countrySelect.value = currentSource;
                    }}
                }}
            }} catch(e) {{
                console.warn("Failed fetching countries:", e);
            }}
        }}

        async function loadChannels(sourceCode) {{
            currentSource = sourceCode;
            channelListEl.innerHTML = `
                <div class="loading-spinner">
                    <i class="fa-solid fa-circle-notch fa-spin"></i>
                    <span>Đang tải danh sách kênh ${{sourceCode.toUpperCase()}}...</span>
                </div>`;

            try {{
                const res = await fetch(`/tvrun/api/channels?source=${{sourceCode}}`);
                const data = await res.json();
                allChannels = data.channels || [];

                const catSet = new Set();
                allChannels.forEach(c => {{
                    if (c.group) {{
                        c.group.split(";").forEach(g => catSet.add(g.trim()));
                    }}
                }});

                const catOpts = ['<option value="ALL">Tất cả thể loại (' + allChannels.length + ')</option>'];
                Array.from(catSet).sort().forEach(cat => {{
                    catOpts.push(`<option value="${{cat}}">${{cat}}</option>`);
                }});
                categorySelect.innerHTML = catOpts.join('');

                filterAndRenderChannels();

                if (filteredChannels.length > 0) {{
                    selectChannelByIndex(0);
                }}
            }} catch(e) {{
                channelListEl.innerHTML = `<div class="loading-spinner"><p style="color:#ef4444;">Không thể tải danh sách kênh</p></div>`;
            }}
        }}

        function filterAndRenderChannels() {{
            const query = searchInput.value.toLowerCase().trim();
            const selectedCat = categorySelect.value;

            filteredChannels = allChannels.filter(c => {{
                const matchName = (c.title || c.name || "").toLowerCase().includes(query);
                const matchGroup = !selectedCat || selectedCat === "ALL" || (c.group && c.group.includes(selectedCat));
                return matchName && matchGroup;
            }});

            if (filteredChannels.length === 0) {{
                channelListEl.innerHTML = `<div class="loading-spinner"><span>Không tìm thấy kênh phù hợp</span></div>`;
                return;
            }}

            channelListEl.innerHTML = filteredChannels.map((c, idx) => {{
                const logo = c.logo || "https://tvrun.online/social-preview.png";
                const isActive = activeIndex === idx;
                return `
                    <div class="channel-item ${{isActive ? 'active' : ''}}" onclick="selectChannelByIndex(${{idx}})">
                        <img src="${{logo}}" onerror="this.src='https://tvrun.online/social-preview.png'" alt="${{c.title}}">
                        <div class="channel-item-info">
                            <div class="channel-item-title">${{c.title || c.name}}</div>
                            <div class="channel-item-desc">
                                <span>${{c.group || 'General'}}</span>
                                <span>•</span>
                                <span>${{c.resolution || 'HD'}}</span>
                            </div>
                        </div>
                        <span class="status-dot"></span>
                    </div>
                `;
            }}).join('');
        }}

        function selectChannelByIndex(index) {{
            if (index < 0 || index >= filteredChannels.length) return;
            activeIndex = index;
            const ch = filteredChannels[index];
            if (ch) {{
                isUsingProxy = false;
                playChannel(ch, false);
                document.querySelectorAll(".channel-item").forEach((el, i) => {{
                    el.classList.toggle("active", i === index);
                }});
            }}
        }}

        function playChannel(ch, useProxy) {{
            activeChannel = ch;
            isUsingProxy = useProxy;
            playerOverlay.classList.remove("show");

            document.getElementById("currentTitle").textContent = ch.title || ch.name;
            document.getElementById("currentLogo").src = ch.logo || "https://tvrun.online/social-preview.png";
            document.getElementById("currentGroup").textContent = ch.group || "General";
            document.getElementById("currentCountry").textContent = ch.country || currentSource.toUpperCase();
            document.getElementById("currentRes").textContent = useProxy ? "Proxy Stream" : (ch.resolution || "Live HLS");

            let streamUrl = ch.url;
            if (useProxy) {{
                streamUrl = `/tvrun/stream_proxy?url=${{encodeURIComponent(ch.url)}}&referer=${{encodeURIComponent('https://tvrun.online/')}}`;
            }}

            if (Hls.isSupported()) {{
                if (hls) {{
                    hls.destroy();
                }}
                hls = new Hls({{
                    enableWorker: true,
                    lowLatencyMode: true,
                    backBufferLength: 60
                }});
                hls.loadSource(streamUrl);
                hls.attachMedia(videoEl);
                hls.on(Hls.Events.MANIFEST_PARSED, function () {{
                    playerOverlay.classList.remove("show");
                    videoEl.play().catch(e => console.log("Autoplay blocked:", e));
                }});
                hls.on(Hls.Events.ERROR, function (event, data) {{
                    if (data.fatal) {{
                        console.warn("HLS fatal error:", data.type, data.details);
                        if (!isUsingProxy) {{
                            console.log("Auto retrying with proxy...");
                            playChannel(ch, true);
                        }} else {{
                            playerOverlay.classList.add("show");
                        }}
                    }}
                }});
            }} else if (videoEl.canPlayType('application/vnd.apple.mpegurl')) {{
                videoEl.src = streamUrl;
                videoEl.addEventListener('loadedmetadata', function () {{
                    playerOverlay.classList.remove("show");
                    videoEl.play().catch(e => console.log("Autoplay blocked:", e));
                }});
                videoEl.onerror = function() {{
                    if (!isUsingProxy) {{
                        playChannel(ch, true);
                    }} else {{
                        playerOverlay.classList.add("show");
                    }}
                }};
            }}
        }}

        function retryWithProxy() {{
            if (activeChannel) {{
                playChannel(activeChannel, true);
            }}
        }}

        function playNextChannel() {{
            if (activeIndex + 1 < filteredChannels.length) {{
                selectChannelByIndex(activeIndex + 1);
            }} else {{
                selectChannelByIndex(0);
            }}
        }}

        function copyStreamUrl() {{
            if (activeChannel && activeChannel.url) {{
                navigator.clipboard.writeText(activeChannel.url).then(() => {{
                    alert("Đã sao chép link stream HLS vào bộ nhớ tạm!");
                }}).catch(() => {{
                    prompt("Link Stream HLS:", activeChannel.url);
                }});
            }}
        }}

        window.onload = init;
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)
