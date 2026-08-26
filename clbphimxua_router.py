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

logger = logging.getLogger("clbphimxua_addon")

clbphimxua_router = APIRouter(prefix="", tags=["clbphimxua"])

CLBPHIMXUA_BASE = "https://clbphimxua.com"

_clb_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
CLB_CACHE_TTL = 600

_clb_client: Optional[httpx.AsyncClient] = None

def get_clb_client() -> httpx.AsyncClient:
    global _clb_client
    if _clb_client is None or _clb_client.is_closed:
        _clb_client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=6.0),
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://clbphimxua.com/"
            }
        )
    return _clb_client

async def clb_fetch_json(url: str, ttl: int = CLB_CACHE_TTL) -> Optional[Any]:
    now = time.time()
    if url in _clb_cache:
        data, exp = _clb_cache[url]
        if now < exp:
            return data

    client = get_clb_client()
    try:
        res = await client.get(url)
        if res.status_code == 200:
            data = res.json()
            if len(_clb_cache) > 500:
                _clb_cache.clear()
            _clb_cache[url] = (data, now + ttl)
            return data
    except Exception as e:
        logger.warning(f"CLBPhimXua fetch json failed for {url}: {e}")
    return None

def clb_post_to_meta(post: dict) -> dict:
    post_id = str(post.get("id", ""))
    slug = post.get("slug", post_id)
    title_obj = post.get("title", {})
    title = title_obj.get("rendered", "") if isinstance(title_obj, dict) else str(title_obj)
    title = re.sub(r'<[^>]+>', '', title).strip()
    
    # Extract embedded featured media (poster)
    poster = None
    embedded = post.get("_embedded", {})
    if isinstance(embedded, dict):
        media_list = embedded.get("wp:featuredmedia", [])
        if media_list and isinstance(media_list, list) and isinstance(media_list[0], dict):
            poster = media_list[0].get("source_url")

    # If no featured media, extract first image from content
    content_obj = post.get("content", {})
    content_html = content_obj.get("rendered", "") if isinstance(content_obj, dict) else ""
    if not poster:
        img_m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content_html)
        if img_m:
            poster = img_m.group(1)

    excerpt_obj = post.get("excerpt", {})
    excerpt = excerpt_obj.get("rendered", "") if isinstance(excerpt_obj, dict) else ""
    desc = re.sub(r'<[^>]+>', '', excerpt or content_html).strip()[:300]

    return {
        "id": f"clbphimxua:{post_id}",
        "type": "movie",
        "name": title,
        "poster": poster,
        "background": poster,
        "posterShape": "regular",
        "description": desc or f"{title} - Phim Xưa & Kinh Điển Vietsub / Lồng Tiếng",
        "genres": ["Phim Kinh Điển", "Phim Xưa", "Vietsub / Lồng Tiếng"]
    }

# ------------------------------------------------------------------
# Manifest Route
# ------------------------------------------------------------------
@clbphimxua_router.get("/clbphimxua/manifest.json")
@clbphimxua_router.get("/manifest.json")
async def clbphimxua_manifest():
    is_board = getattr(Config, "ENABLE_BOARD_CLBPHIMXUA", True)
    catalogs = [
        {
            "type": "movie",
            "id": "clbphimxua_all",
            "name": "📼 CLB Phim Xưa & Kinh Điển",
            "extra": [
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        }
    ]
    if not is_board:
        for cat in catalogs:
            cat["extra"].append({"name": "genre", "isRequired": False, "options": ["Khám Phá"]})

    return {
        "id": "community.clbphimxua.cinema",
        "version": "1.0.0",
        "name": "CLB Phim Xưa & Kinh Điển",
        "description": "Kho phim kinh điển, phim xưa truyền hình Việt Nam & Châu Á",
        "logo": "https://raw.githubusercontent.com/Stremio/stremio-addon-sdk/master/logo.png",
        "resources": ["catalog", "meta", "stream"],
        "types": ["movie"],
        "idPrefixes": ["clbphimxua:"],
        "catalogs": catalogs
    }

# ------------------------------------------------------------------
# Catalog Route
# ------------------------------------------------------------------
@clbphimxua_router.get("/clbphimxua/catalog/{type}/{id}.json")
@clbphimxua_router.get("/clbphimxua/catalog/{type}/{id}/{extra}.json")
@clbphimxua_router.get("/catalog/{type}/{id}.json")
@clbphimxua_router.get("/catalog/{type}/{id}/{extra}.json")
async def clbphimxua_catalog_handler(type: str, id: str, extra: Optional[str] = None):
    skip = 0
    search_query = None
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

    page = (skip // 20) + 1
    if search_query:
        url = f"{CLBPHIMXUA_BASE}/wp-json/wp/v2/posts?search={urllib.parse.quote(search_query)}&per_page=20&page={page}&_embed"
    else:
        url = f"{CLBPHIMXUA_BASE}/wp-json/wp/v2/posts?per_page=20&page={page}&_embed"

    posts = await clb_fetch_json(url)
    metas = []
    if isinstance(posts, list):
        metas = [clb_post_to_meta(p) for p in posts if isinstance(p, dict)]
    return {"metas": metas}

# ------------------------------------------------------------------
# Meta Route
# ------------------------------------------------------------------
@clbphimxua_router.get("/clbphimxua/meta/{type}/{id}.json")
@clbphimxua_router.get("/meta/{type}/{id}.json")
async def clbphimxua_meta_handler(type: str, id: str):
    post_id = id.replace("clbphimxua:", "")
    url = f"{CLBPHIMXUA_BASE}/wp-json/wp/v2/posts/{post_id}?_embed"
    post = await clb_fetch_json(url)
    if not post or not isinstance(post, dict):
        return {"meta": {}}

    meta = clb_post_to_meta(post)
    return {"meta": meta}

# ------------------------------------------------------------------
# Stream Route
# ------------------------------------------------------------------
@clbphimxua_router.get("/clbphimxua/stream/{type}/{id}.json")
@clbphimxua_router.get("/stream/{type}/{id}.json")
async def clbphimxua_stream_handler(type: str, id: str):
    post_id = id.replace("clbphimxua:", "")
    url = f"{CLBPHIMXUA_BASE}/wp-json/wp/v2/posts/{post_id}?_embed"
    post = await clb_fetch_json(url)
    if not post or not isinstance(post, dict):
        return {"streams": []}

    content_obj = post.get("content", {})
    content = content_obj.get("rendered", "") if isinstance(content_obj, dict) else ""
    
    # Find all iframes and video links
    iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', content)
    video_links = re.findall(r'href=["\']([^"\']+\.(?:m3u8|mp4|mkv))["\']', content)
    
    streams = []
    for idx, v_url in enumerate(video_links, 1):
        streams.append({
            "name": f"📼 CLB Phim Xưa Direct #{idx}",
            "title": f"Video Link #{idx}\nDirect Stream",
            "url": v_url
        })

    for idx, if_url in enumerate(iframes, 1):
        streams.append({
            "name": f"🌐 CLB Phim Xưa Web #{idx}",
            "title": f"Web Player Embed #{idx}",
            "externalUrl": if_url
        })

    if not streams and post.get("link"):
        streams.append({
            "name": "🌐 CLB Phim Xưa Web",
            "title": "Mở trang xem phim gốc",
            "externalUrl": post.get("link")
        })

    return {"streams": streams}

# ------------------------------------------------------------------
# Search Helper for Dashboard
# ------------------------------------------------------------------
async def search_clbphimxua(query: str, max_results: int = 15) -> List[Dict[str, Any]]:
    results = []
    try:
        url = f"{CLBPHIMXUA_BASE}/wp-json/wp/v2/posts?search={urllib.parse.quote(query)}&per_page={max_results}&_embed"
        posts = await clb_fetch_json(url)
        if isinstance(posts, list):
            for p in posts[:max_results]:
                if isinstance(p, dict):
                    m = clb_post_to_meta(p)
                    results.append(m)
    except Exception as e:
        logger.warning(f"CLBPhimXua search error: {e}")
    return results
