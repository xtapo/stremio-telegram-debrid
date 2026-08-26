from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse, Response
import httpx
import urllib.parse
import re
import logging
import time
import asyncio
from typing import Optional, Dict, Any, Tuple, List
from config import Config

logger = logging.getLogger("kkphim_addon")

kkphim_router = APIRouter(prefix="", tags=["kkphim"])

KKPHIM_API_BASE = "https://phimapi.com"
KKPHIM_IMG_BASE = "https://phimimg.com"

# In-memory cache
_kkphim_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
KKPHIM_CACHE_TTL = 600  # 10 minutes

_kkphim_client: Optional[httpx.AsyncClient] = None

def get_kkphim_client() -> httpx.AsyncClient:
    global _kkphim_client
    if _kkphim_client is None or _kkphim_client.is_closed:
        _kkphim_client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=6.0),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=30, max_connections=60),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
    return _kkphim_client

async def kkphim_fetch_json(url: str, ttl: int = KKPHIM_CACHE_TTL) -> Optional[dict]:
    now = time.time()
    if url in _kkphim_cache:
        data, exp = _kkphim_cache[url]
        if now < exp:
            return data

    client = get_kkphim_client()
    for attempt in range(2):
        try:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json()
                if len(_kkphim_cache) > 500:
                    _kkphim_cache.clear()
                _kkphim_cache[url] = (data, now + ttl)
                return data
            elif res.status_code == 404:
                return None
            else:
                if attempt == 0:
                    await asyncio.sleep(0.3)
                    continue
                return None
        except Exception as e:
            if attempt == 0:
                await asyncio.sleep(0.3)
                continue
            logger.warning(f"KKPhim fetch failed for {url}: {e}")
            return None
    return None

# ------------------------------------------------------------------
# Manifest Catalogs & Genre Maps
# ------------------------------------------------------------------
KKPHIM_GENRES_MAP = {
    "Hành Động": "hanh-dong",
    "Tình Cảm": "tinh-cam",
    "Hài Hước": "hai-huoc",
    "Kinh Dị": "kinh-di",
    "Hoạt Hình": "hoat-hinh",
    "Cổ Trang": "co-trang",
    "Võ Thuật": "vo-thuat",
    "Viễn Tưởng": "vien-tuong",
    "Phiêu Lưu": "phieu-luu",
    "Hình Sự": "hinh-su",
    "Tâm Lý": "tam-ly",
    "Học Đường": "hoc-duong",
    "Bí Ẩn": "bi-an",
    "Gia Đình": "gia-dinh",
    "Thần Thoại": "than-thoai",
    "Chiến Tranh": "chien-tranh",
    "Tài Liệu": "tai-lieu",
    "Chính Kịch": "chinh-kich",
    "Âm Nhạc": "am-nhac",
    "Khoa Học": "khoa-hoc",
    "Phim 18+": "phim-18"
}

KKPHIM_COUNTRIES_MAP = {
    "Trung Quốc": "trung-quoc",
    "Hàn Quốc": "han-quoc",
    "Âu Mỹ": "au-my",
    "Nhật Bản": "nhat-ban",
    "Thái Lan": "thai-lan",
    "Việt Nam": "viet-nam",
    "Đài Loan": "dai-loan",
    "Hồng Kông": "hong-kong",
    "Ấn Độ": "an-do",
    "Anh": "anh",
    "Pháp": "phap",
    "Canada": "canada",
    "Đức": "duc",
    "Tây Ban Nha": "tay-ban-nha",
    "Nga": "nga",
    "Úc": "uc",
    "Indonesia": "indonesia",
    "Philippines": "philippines"
}

KKPHIM_YEARS = [str(y) for y in range(2026, 2010, -1)]

def format_img_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"{KKPHIM_IMG_BASE}{url}"
    return f"{KKPHIM_IMG_BASE}/{url}"

def kkphim_item_to_meta(item: dict) -> dict:
    slug = item.get("slug", "")
    name = item.get("name", "")
    origin_name = item.get("origin_name", "")
    year_str = str(item.get("year", "")) if item.get("year") else ""
    type_str = item.get("type", "")
    stremio_type = "series" if type_str in ["series", "hoathinh", "tvshows"] or (item.get("episode_total") and str(item.get("episode_total")) != "1" and str(item.get("episode_total")) != "") else "movie"
    
    poster = format_img_url(item.get("poster_url") or item.get("thumb_url"))
    thumb = format_img_url(item.get("thumb_url") or item.get("poster_url"))
    
    # Genres & Countries
    genres = [g.get("name") for g in item.get("category", []) if isinstance(g, dict) and g.get("name")]
    countries = [c.get("name") for c in item.get("country", []) if isinstance(c, dict) and c.get("name")]
    
    quality = item.get("quality", "HD")
    lang = item.get("lang", "Vietsub")
    ep_curr = item.get("episode_current", "")
    
    genres_display = list(genres)
    if quality:
        genres_display.insert(0, quality)
    if lang:
        genres_display.insert(1, lang)
    if ep_curr and stremio_type == "series":
        genres_display.insert(2, ep_curr)

    description = item.get("content") or ""
    # Clean HTML tags
    description = re.sub(r'<[^>]+>', '', description).strip()
    
    name_display = name
    if origin_name and origin_name.lower() != name.lower():
        name_display = f"{name} ({origin_name})"

    meta = {
        "id": f"kkphim:{slug}",
        "type": stremio_type,
        "name": name_display,
        "poster": poster or thumb,
        "background": thumb or poster,
        "posterShape": "regular",
        "description": description or f"{name} ({origin_name}) - {year_str}",
        "genres": genres_display,
        "releaseInfo": year_str,
    }
    
    return meta

# ------------------------------------------------------------------
# Manifest Route
# ------------------------------------------------------------------
@kkphim_router.get("/kkphim/manifest.json")
@kkphim_router.get("/manifest.json")
async def kkphim_manifest():
    is_board = getattr(Config, "ENABLE_BOARD_KKPHIM", True)
    
    catalogs = [
        {
            "type": "movie",
            "id": "kkphim_phim_le",
            "name": "🎬 KKPhim: Phim Lẻ Mới",
            "extra": [
                {"name": "genre", "isRequired": False, "options": list(KKPHIM_GENRES_MAP.keys())},
                {"name": "skip", "isRequired": False},
                {"name": "search", "isRequired": False}
            ]
        },
        {
            "type": "series",
            "id": "kkphim_phim_bo",
            "name": "📺 KKPhim: Phim Bộ Đang Hot",
            "extra": [
                {"name": "genre", "isRequired": False, "options": list(KKPHIM_GENRES_MAP.keys())},
                {"name": "skip", "isRequired": False},
                {"name": "search", "isRequired": False}
            ]
        },
        {
            "type": "series",
            "id": "kkphim_hoat_hinh",
            "name": "⛩️ KKPhim: Hoạt Hình & Anime",
            "extra": [
                {"name": "genre", "isRequired": False, "options": list(KKPHIM_GENRES_MAP.keys())},
                {"name": "skip", "isRequired": False},
                {"name": "search", "isRequired": False}
            ]
        },
        {
            "type": "series",
            "id": "kkphim_tv_shows",
            "name": "🎤 KKPhim: TV Shows & Game Show",
            "extra": [
                {"name": "skip", "isRequired": False},
                {"name": "search", "isRequired": False}
            ]
        }
    ]
    
    if not is_board:
        for cat in catalogs:
            cat["extra"].append({"name": "genre", "isRequired": False, "options": ["Khám Phá"]})

    return {
        "id": "community.kkphim.cinema",
        "version": "1.0.0",
        "name": "KKPhim Cinema Vietsub",
        "description": "Kho phim Vietsub, Thuyết minh, Lồng tiếng chất lượng cao từ KKPhim & PhimAPI",
        "logo": "https://raw.githubusercontent.com/Stremio/stremio-addon-sdk/master/logo.png",
        "resources": ["catalog", "meta", "stream"],
        "types": ["movie", "series"],
        "idPrefixes": ["kkphim:"],
        "catalogs": catalogs
    }

# ------------------------------------------------------------------
# Stream Proxy
# ------------------------------------------------------------------
@kkphim_router.get("/kkphim/stream_proxy")
async def kkphim_stream_proxy(request: Request, url: str, referer: Optional[str] = None):
    """Proxy for HLS m3u8 or ts streams if needed."""
    try:
        decoded_url = urllib.parse.unquote(url)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": referer or "https://kkphim.com/"
        }
        client = get_kkphim_client()
        res = await client.get(decoded_url, headers=headers)
        return Response(
            content=res.content,
            status_code=res.status_code,
            headers={
                "Content-Type": res.headers.get("Content-Type", "application/vnd.apple.mpegurl"),
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )
    except Exception as e:
        logger.error(f"KKPhim stream proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ------------------------------------------------------------------
# Catalog Route
# ------------------------------------------------------------------
@kkphim_router.get("/kkphim/catalog/{type}/{id}.json")
@kkphim_router.get("/kkphim/catalog/{type}/{id}/{extra}.json")
@kkphim_router.get("/catalog/{type}/{id}.json")
@kkphim_router.get("/catalog/{type}/{id}/{extra}.json")
async def kkphim_catalog_handler(type: str, id: str, extra: Optional[str] = None):
    skip = 0
    search_query = None
    genre_selected = None
    
    if extra:
        extra_parts = urllib.parse.unquote(extra).split("&")
        for part in extra_parts:
            if "=" in part:
                k, v = part.split("=", 1)
                if k == "skip":
                    try:
                        skip = int(v)
                    except ValueError:
                        pass
                elif k == "search":
                    search_query = v.strip()
                elif k == "genre":
                    genre_selected = v.strip()

    page = (skip // 24) + 1
    
    # 1. Search Query
    if search_query:
        url = f"{KKPHIM_API_BASE}/v1/api/tim-kiem?keyword={urllib.parse.quote(search_query)}&page={page}&limit=24"
        data = await kkphim_fetch_json(url)
        items = data.get("data", {}).get("items", []) if data else []
        metas = [kkphim_item_to_meta(it) for it in items]
        return {"metas": metas}

    # 2. Genre Selected
    if genre_selected and genre_selected in KKPHIM_GENRES_MAP:
        genre_slug = KKPHIM_GENRES_MAP[genre_selected]
        url = f"{KKPHIM_API_BASE}/v1/api/the-loai/{genre_slug}?page={page}&limit=24"
        data = await kkphim_fetch_json(url)
        items = data.get("data", {}).get("items", []) if data else []
        metas = [kkphim_item_to_meta(it) for it in items]
        return {"metas": metas}

    # 3. Standard Catalogs
    if id == "kkphim_phim_le":
        url = f"{KKPHIM_API_BASE}/v1/api/danh-sach/phim-le?page={page}&limit=24"
    elif id == "kkphim_phim_bo":
        url = f"{KKPHIM_API_BASE}/v1/api/danh-sach/phim-bo?page={page}&limit=24"
    elif id == "kkphim_hoat_hinh":
        url = f"{KKPHIM_API_BASE}/v1/api/danh-sach/hoat-hinh?page={page}&limit=24"
    elif id == "kkphim_tv_shows":
        url = f"{KKPHIM_API_BASE}/v1/api/danh-sach/tv-shows?page={page}&limit=24"
    else:
        # Default: Phim mới cập nhật
        url = f"{KKPHIM_API_BASE}/danh-sach/phim-moi-cap-nhat?page={page}"

    data = await kkphim_fetch_json(url)
    items = []
    if data:
        if "data" in data and isinstance(data["data"], dict) and "items" in data["data"]:
            items = data["data"]["items"]
        elif "items" in data:
            items = data["items"]

    metas = [kkphim_item_to_meta(it) for it in items]
    return {"metas": metas}

# ------------------------------------------------------------------
# Meta Route
# ------------------------------------------------------------------
@kkphim_router.get("/kkphim/meta/{type}/{id}.json")
@kkphim_router.get("/meta/{type}/{id}.json")
async def kkphim_meta_handler(type: str, id: str):
    slug = id.replace("kkphim:", "")
    url = f"{KKPHIM_API_BASE}/phim/{slug}"
    data = await kkphim_fetch_json(url)
    if not data or "movie" not in data:
        return {"meta": {}}

    movie = data["movie"]
    meta = kkphim_item_to_meta(movie)
    
    # Cast & Director
    if movie.get("actor"):
        meta["cast"] = [a.strip() for a in movie["actor"] if isinstance(a, str) and a.strip()]
    if movie.get("director"):
        meta["director"] = [d.strip() for d in movie["director"] if isinstance(d, str) and d.strip()]

    # Video episodes structure for series
    episodes_data = data.get("episodes", [])
    if meta["type"] == "series" and episodes_data:
        videos = []
        # Use first server as primary ep index
        primary_server = episodes_data[0]
        ep_items = primary_server.get("server_data", []) or primary_server.get("items", [])
        for idx, ep in enumerate(ep_items, 1):
            ep_name = ep.get("name", str(idx))
            ep_slug = ep.get("slug", f"tap-{idx}")
            videos.append({
                "id": f"kkphim:{slug}:0:{ep_slug}",
                "title": f"Tập {ep_name}",
                "season": 1,
                "episode": idx,
                "released": movie.get("modified", {}).get("time") if isinstance(movie.get("modified"), dict) else None
            })
        meta["videos"] = videos

    return {"meta": meta}

# ------------------------------------------------------------------
# Stream Route
# ------------------------------------------------------------------
@kkphim_router.get("/kkphim/stream/{type}/{id}.json")
@kkphim_router.get("/stream/{type}/{id}.json")
async def kkphim_stream_handler(type: str, id: str):
    # Formats:
    # 1. kkphim:{slug} (Movie)
    # 2. kkphim:{slug}:{server_idx}:{ep_slug} (Series episode)
    
    slug = id.replace("kkphim:", "")
    target_server_idx = 0
    target_ep_slug = None
    
    parts = slug.split(":")
    if len(parts) >= 3:
        slug = parts[0]
        try:
            target_server_idx = int(parts[1])
        except ValueError:
            target_server_idx = 0
        target_ep_slug = parts[2]
    elif len(parts) == 2:
        slug = parts[0]
        target_ep_slug = parts[1]

    url = f"{KKPHIM_API_BASE}/phim/{slug}"
    data = await kkphim_fetch_json(url)
    if not data or "episodes" not in data:
        return {"streams": []}

    movie = data.get("movie", {})
    movie_title = movie.get("name", slug)
    episodes_groups = data.get("episodes", [])
    
    streams = []
    
    for s_idx, ep_group in enumerate(episodes_groups):
        server_name = ep_group.get("server_name", f"VIP #{s_idx+1}")
        ep_list = ep_group.get("server_data", []) or ep_group.get("items", [])
        
        target_ep = None
        if target_ep_slug:
            for ep in ep_list:
                if str(ep.get("slug")) == target_ep_slug or str(ep.get("name")) == target_ep_slug:
                    target_ep = ep
                    break
            # Fallback to first if matching index
            if not target_ep and ep_list:
                try:
                    num_idx = int(re.sub(r'\D', '', target_ep_slug)) - 1
                    if 0 <= num_idx < len(ep_list):
                        target_ep = ep_list[num_idx]
                except Exception:
                    pass
        else:
            # Movie: Take first episode
            if ep_list:
                target_ep = ep_list[0]

        if target_ep:
            m3u8_url = target_ep.get("link_m3u8")
            embed_url = target_ep.get("link_embed")
            ep_title = target_ep.get("name", "1")
            
            if m3u8_url:
                streams.append({
                    "name": f"⚡ KKPhim [{server_name}]",
                    "title": f"{movie_title} - Tập {ep_title}\n🏎️ Direct HLS 1080p Ultra Fast",
                    "url": m3u8_url,
                    "behaviorHints": {
                        "notWebReady": False,
                        "proxyHeaders": {
                            "request": {
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                                "Referer": "https://kkphim.com/"
                            }
                        }
                    }
                })
            elif embed_url:
                streams.append({
                    "name": f"🌐 KKPhim Web [{server_name}]",
                    "title": f"{movie_title} - Tập {ep_title}\n(Embed Web Player)",
                    "externalUrl": embed_url
                })

    return {"streams": streams}

# ------------------------------------------------------------------
# Search Helper for Dashboard
# ------------------------------------------------------------------
async def search_kkphim(query: str, max_results: int = 15) -> List[Dict[str, Any]]:
    results = []
    try:
        url = f"{KKPHIM_API_BASE}/v1/api/tim-kiem?keyword={urllib.parse.quote(query)}&limit={max_results}"
        data = await kkphim_fetch_json(url)
        items = data.get("data", {}).get("items", []) if data else []
        for it in items[:max_results]:
            m = kkphim_item_to_meta(it)
            results.append(m)
    except Exception as e:
        logger.warning(f"KKPhim search error: {e}")
    return results
