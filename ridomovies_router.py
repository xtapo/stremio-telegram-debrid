from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, Response
import httpx
import urllib.parse
import re
import logging
import time
import asyncio
from typing import Optional, Dict, Any, Tuple, List
from config import Config

logger = logging.getLogger("ridomovies_addon")

ridomovies_router = APIRouter(prefix="", tags=["ridomovies"])

RIDOMOVIES_BASE = "https://ridomovies.su"

_ridomovies_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
RIDOMOVIES_CACHE_TTL = 600  # 10 minutes

_rido_client: Optional[httpx.AsyncClient] = None

def get_rido_client() -> httpx.AsyncClient:
    global _rido_client
    if _rido_client is None or _rido_client.is_closed:
        _rido_client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=6.0),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=40),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://ridomovies.su/",
                "Origin": "https://ridomovies.su"
            }
        )
    return _rido_client

async def ridomovies_fetch_json(url: str, ttl: int = RIDOMOVIES_CACHE_TTL) -> Optional[dict]:
    now = time.time()
    if url in _ridomovies_cache:
        data, exp = _ridomovies_cache[url]
        if now < exp:
            return data

    try:
        client = get_rido_client()
        res = await client.get(url)
        if res.status_code == 200:
            data = res.json()
            if len(_ridomovies_cache) > 500:
                _ridomovies_cache.clear()
            _ridomovies_cache[url] = (data, now + ttl)
            return data
    except Exception as e:
        logger.warning(f"RidoMovies fetch json failed for {url}: {e}")
    return None

async def ridomovies_fetch_text(url: str) -> str:
    try:
        client = get_rido_client()
        res = await client.get(url)
        if res.status_code == 200:
            return res.text
    except Exception as e:
        logger.warning(f"RidoMovies fetch html failed for {url}: {e}")
    return ""

def rido_item_to_meta(item: dict) -> dict:
    slug = item.get("slug", "")
    title = item.get("title", "")
    year_str = str(item.get("year", "")) if item.get("year") else ""
    rido_type = item.get("type", "movie")
    stremio_type = "series" if rido_type in ["tv", "series"] else "movie"
    
    poster = item.get("poster")
    if poster and not poster.startswith("http"):
        poster = f"{RIDOMOVIES_BASE}{poster}" if poster.startswith("/") else f"{RIDOMOVIES_BASE}/{poster}"

    return {
        "id": f"ridomovies:{slug}",
        "type": stremio_type,
        "name": title,
        "poster": poster,
        "background": poster,
        "posterShape": "regular",
        "description": f"{title} ({year_str}) - Watch on RidoMovies English 1080p",
        "releaseInfo": year_str,
        "genres": ["English", "HD", "4K UHD" if "4k" in title.lower() else "1080p"]
    }

# ------------------------------------------------------------------
# Manifest Route
# ------------------------------------------------------------------
@ridomovies_router.get("/ridomovies/manifest.json")
@ridomovies_router.get("/manifest.json")
async def ridomovies_manifest():
    is_board = getattr(Config, "ENABLE_BOARD_RIDOMOVIES", True)
    catalogs = [
        {
            "type": "movie",
            "id": "ridomovies_movies",
            "name": "🎬 RidoMovies: Popular Movies",
            "extra": [
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        },
        {
            "type": "series",
            "id": "ridomovies_series",
            "name": "📺 RidoMovies: Top TV Series",
            "extra": [
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        }
    ]
    if not is_board:
        for cat in catalogs:
            cat["extra"].append({"name": "genre", "isRequired": False, "options": ["Discover"]})

    return {
        "id": "community.ridomovies.english",
        "version": "1.0.0",
        "name": "RidoMovies Cinema English",
        "description": "Watch popular English movies and TV series in HD/4K from RidoMovies",
        "logo": "https://raw.githubusercontent.com/Stremio/stremio-addon-sdk/master/logo.png",
        "resources": ["catalog", "meta", "stream"],
        "types": ["movie", "series"],
        "idPrefixes": ["ridomovies:"],
        "catalogs": catalogs
    }

# ------------------------------------------------------------------
# Catalog Route
# ------------------------------------------------------------------
@ridomovies_router.get("/ridomovies/catalog/{type}/{id}.json")
@ridomovies_router.get("/ridomovies/catalog/{type}/{id}/{extra}.json")
@ridomovies_router.get("/catalog/{type}/{id}.json")
@ridomovies_router.get("/catalog/{type}/{id}/{extra}.json")
async def ridomovies_catalog_handler(type: str, id: str, extra: Optional[str] = None):
    search_query = None
    if extra:
        extra_parts = urllib.parse.unquote(extra).split("&")
        for part in extra_parts:
            if "=" in part:
                k, v = part.split("=", 1)
                if k == "search":
                    search_query = v.strip()

    if search_query:
        url = f"{RIDOMOVIES_BASE}/api/search?q={urllib.parse.quote(search_query)}"
        data = await ridomovies_fetch_json(url)
        items = data.get("data", []) if data else []
        metas = [rido_item_to_meta(it) for it in items]
        return {"metas": metas}

    # Popular fallback
    url = f"{RIDOMOVIES_BASE}/api/search?q=2024"
    data = await ridomovies_fetch_json(url)
    items = data.get("data", []) if data else []
    metas = [rido_item_to_meta(it) for it in items]
    return {"metas": metas}

# ------------------------------------------------------------------
# Meta Route
# ------------------------------------------------------------------
@ridomovies_router.get("/ridomovies/meta/{type}/{id}.json")
@ridomovies_router.get("/meta/{type}/{id}.json")
async def ridomovies_meta_handler(type: str, id: str):
    slug = id.replace("ridomovies:", "")
    # Check page
    url = f"{RIDOMOVIES_BASE}/movies/{slug}" if type == "movie" else f"{RIDOMOVIES_BASE}/tv/{slug}"
    html = await ridomovies_fetch_text(url)
    if not html:
        url = f"{RIDOMOVIES_BASE}/movies/{slug}"
        html = await ridomovies_fetch_text(url)

    title_m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
    title = title_m.group(1).strip() if title_m else slug.replace("-", " ").title()
    poster_m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html)
    poster = poster_m.group(1) if poster_m else None
    desc_m = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', html)
    desc = desc_m.group(1) if desc_m else f"{title} - Watch on RidoMovies"

    meta = {
        "id": f"ridomovies:{slug}",
        "type": type,
        "name": title,
        "poster": poster,
        "background": poster,
        "posterShape": "regular",
        "description": desc,
        "genres": ["English", "HD", "Action"]
    }
    return {"meta": meta}

# ------------------------------------------------------------------
# Stream Route
# ------------------------------------------------------------------
@ridomovies_router.get("/ridomovies/stream/{type}/{id}.json")
@ridomovies_router.get("/stream/{type}/{id}.json")
async def ridomovies_stream_handler(type: str, id: str):
    slug = id.replace("ridomovies:", "")
    url = f"{RIDOMOVIES_BASE}/movies/{slug}" if type == "movie" else f"{RIDOMOVIES_BASE}/tv/{slug}"
    html = await ridomovies_fetch_text(url)
    if not html:
        url = f"{RIDOMOVIES_BASE}/movies/{slug}"
        html = await ridomovies_fetch_text(url)

    iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html)
    streams = []
    
    for idx, iframe_url in enumerate(iframes, 1):
        if not iframe_url.startswith("http"):
            iframe_url = f"https:{iframe_url}" if iframe_url.startswith("//") else f"{RIDOMOVIES_BASE}{iframe_url}"
        
        streams.append({
            "name": f"🌐 RidoMovies HD #{idx}",
            "title": f"RidoMovies English Server #{idx}\n(Embed Stream)",
            "externalUrl": iframe_url
        })

    # If no iframe found in direct HTML, check data-src or close-load
    closeload_m = re.search(r'(https?://closeload\.[^"\'\s]+)', html)
    if closeload_m:
        cl_url = closeload_m.group(1)
        streams.append({
            "name": "⚡ RidoMovies CloseLoad VIP",
            "title": "Fast English Stream Server (CloseLoad)",
            "externalUrl": cl_url
        })

    return {"streams": streams}

# ------------------------------------------------------------------
# Search Helper for Dashboard
# ------------------------------------------------------------------
async def search_ridomovies(query: str, max_results: int = 15) -> List[Dict[str, Any]]:
    results = []
    try:
        url = f"{RIDOMOVIES_BASE}/api/search?q={urllib.parse.quote(query)}"
        data = await ridomovies_fetch_json(url)
        items = data.get("data", []) if data else []
        for it in items[:max_results]:
            m = rido_item_to_meta(it)
            results.append(m)
    except Exception as e:
        logger.warning(f"RidoMovies search error: {e}")
    return results
