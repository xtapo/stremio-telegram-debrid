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

logger = logging.getLogger("yanhh3d_addon")

yanhh3d_router = APIRouter(prefix="", tags=["yanhh3d"])

YANHH3D_BASE = "https://yanhh3d.run"

_yanhh_cache: Dict[str, Tuple[Any, float]] = {}
YANHH_CACHE_TTL = 600

_yanhh_client: Optional[httpx.AsyncClient] = None

def get_yanhh_client() -> httpx.AsyncClient:
    global _yanhh_client
    if _yanhh_client is None or _yanhh_client.is_closed:
        _yanhh_client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=6.0),
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://yanhh3d.run/"
            }
        )
    return _yanhh_client

async def yanhh_fetch_html(url: str, ttl: int = YANHH_CACHE_TTL) -> str:
    now = time.time()
    if url in _yanhh_cache:
        data, exp = _yanhh_cache[url]
        if now < exp:
            return data

    client = get_yanhh_client()
    try:
        res = await client.get(url)
        if res.status_code == 200:
            text = res.text
            if len(_yanhh_cache) > 500:
                _yanhh_cache.clear()
            _yanhh_cache[url] = (text, now + ttl)
            return text
    except Exception as e:
        logger.warning(f"Yanhh3d fetch failed for {url}: {e}")
    return ""

def parse_yanhh_cards(html: str) -> List[Dict[str, Any]]:
    metas = []
    # Match flw-item cards using boundary lookahead
    card_blocks = re.findall(r'<div class="flw-item">([\s\S]*?)(?=<div class="flw-item"|</div>\s*<div class="clearfix">|<div class="pre-pagination)', html)
    seen = set()
    for block in card_blocks:
        href_m = re.search(r'<a[^>]+href=["\']([^"\']+)["\']', block)
        if not href_m:
            continue
        href = href_m.group(1)
        slug = href.rstrip("/").split("/")[-1]
        if not slug or slug in seen or slug in ["hoat-hinh-4k", "hoat-hinh-2d", "hoan-thanh"]:
            continue
        seen.add(slug)

        img_m = re.search(r'<img[^>]+(?:data-src|src)=["\']([^"\']+)["\']', block)
        poster = img_m.group(1) if img_m else ""
        if poster and not poster.startswith("http"):
            poster = f"{YANHH3D_BASE}{poster}" if poster.startswith("/") else f"{YANHH3D_BASE}/{poster}"

        title_m = re.search(r'<h3 class="film-name">[\s\S]*?<a[^>]*>([^<]+)</a>', block)
        title_clean = title_m.group(1).strip() if title_m else slug.replace("-", " ").title()

        rate_m = re.search(r'<div class="tick[^"]*">([^<]+)</div>', block)
        rate_info = rate_m.group(1).strip() if rate_m else "4K Ultra HD"

        metas.append({
            "id": f"yanhh3d:{slug}",
            "type": "series",
            "name": title_clean,
            "poster": poster,
            "background": poster,
            "posterShape": "regular",
            "description": f"{title_clean} ({rate_info}) - Hoạt Hình 3D Trung Quốc Vietsub 4K",
            "genres": ["Hoạt Hình 3D", "Donghua", rate_info, "Vietsub"]
        })
    return metas

# ------------------------------------------------------------------
# Manifest Route
# ------------------------------------------------------------------
@yanhh3d_router.get("/yanhh3d/manifest.json")
@yanhh3d_router.get("/manifest.json")
async def yanhh3d_manifest():
    is_board = getattr(Config, "ENABLE_BOARD_YANHH3D", True)
    catalogs = [
        {
            "type": "series",
            "id": "yanhh3d_4k",
            "name": "🐲 Yanhh3d: Hoạt Hình 3D 4K",
            "extra": [
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        },
        {
            "type": "series",
            "id": "yanhh3d_completed",
            "name": "🏆 Yanhh3d: Trọn Bộ Hoàn Thành",
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
        "id": "community.yanhh3d.anime",
        "version": "1.0.0",
        "name": "Yanhh3d Anime 3D Donghua",
        "description": "Kho hoạt hình 3D Trung Quốc (Donghua) Vietsub 4K mới nhất",
        "logo": "https://raw.githubusercontent.com/Stremio/stremio-addon-sdk/master/logo.png",
        "resources": ["catalog", "meta", "stream"],
        "types": ["series"],
        "idPrefixes": ["yanhh3d:"],
        "catalogs": catalogs
    }

# ------------------------------------------------------------------
# Catalog Route
# ------------------------------------------------------------------
@yanhh3d_router.get("/yanhh3d/catalog/{type}/{id}.json")
@yanhh3d_router.get("/yanhh3d/catalog/{type}/{id}/{extra}.json")
@yanhh3d_router.get("/catalog/{type}/{id}.json")
@yanhh3d_router.get("/catalog/{type}/{id}/{extra}.json")
async def yanhh3d_catalog_handler(type: str, id: str, extra: Optional[str] = None):
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
        url = f"{YANHH3D_BASE}/search?keysearch={urllib.parse.quote(search_query)}"
    elif id == "yanhh3d_completed":
        url = f"{YANHH3D_BASE}/hoan-thanh?page={page}"
    else:
        url = f"{YANHH3D_BASE}/hoat-hinh-4k?page={page}"

    html = await yanhh_fetch_html(url)
    metas = parse_yanhh_cards(html)
    return {"metas": metas}

# ------------------------------------------------------------------
# Meta Route
# ------------------------------------------------------------------
@yanhh3d_router.get("/yanhh3d/meta/{type}/{id}.json")
@yanhh3d_router.get("/meta/{type}/{id}.json")
async def yanhh3d_meta_handler(type: str, id: str):
    slug = id.replace("yanhh3d:", "")
    url = f"{YANHH3D_BASE}/{slug}"
    html = await yanhh_fetch_html(url)
    if not html:
        return {"meta": {}}

    title_m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
    title = title_m.group(1).strip() if title_m else slug.replace("-", " ").title()
    poster_m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html)
    poster = poster_m.group(1) if poster_m else None
    desc_m = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', html)
    desc = desc_m.group(1) if desc_m else f"{title} - Hoạt hình 3D Donghua Vietsub"

    # Extract episode links
    # Examples: <a href="/slug/tap-1">Tập 1</a> or data-ep
    ep_matches = re.findall(r'<a[^>]+href=["\'](/[^"\']*/tap-[^"\']+)["\'][^>]*>([^<]+)</a>', html)
    videos = []
    seen_eps = set()
    for ep_href, ep_name in ep_matches:
        ep_slug = ep_href.strip("/").split("/")[-1]
        if ep_slug not in seen_eps:
            seen_eps.add(ep_slug)
            num_m = re.search(r'\d+', ep_name)
            ep_num = int(num_m.group(0)) if num_m else len(videos) + 1
            videos.append({
                "id": f"yanhh3d:{slug}:{ep_slug}",
                "title": ep_name.strip(),
                "season": 1,
                "episode": ep_num
            })

    meta = {
        "id": f"yanhh3d:{slug}",
        "type": "series",
        "name": title,
        "poster": poster,
        "background": poster,
        "posterShape": "regular",
        "description": desc,
        "genres": ["Hoạt Hình 3D", "Donghua", "4K Ultra HD"],
        "videos": videos
    }
    return {"meta": meta}

# ------------------------------------------------------------------
# Stream Route
# ------------------------------------------------------------------
@yanhh3d_router.get("/yanhh3d/stream/{type}/{id}.json")
@yanhh3d_router.get("/stream/{type}/{id}.json")
async def yanhh3d_stream_handler(type: str, id: str):
    slug_part = id.replace("yanhh3d:", "")
    parts = slug_part.split(":")
    if len(parts) >= 2:
        parent_slug = parts[0]
        ep_slug = parts[1]
        url = f"{YANHH3D_BASE}/{parent_slug}/{ep_slug}"
    else:
        url = f"{YANHH3D_BASE}/{slug_part}"

    html = await yanhh_fetch_html(url)
    streams = []

    # Look for m3u8 in script or iframe
    m3u8_matches = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', html)
    for idx, m3u8_url in enumerate(m3u8_matches, 1):
        streams.append({
            "name": f"⚡ Yanhh3d 4K Direct #{idx}",
            "title": f"Donghua 4K Fast Stream #{idx}\nDirect HLS",
            "url": m3u8_url,
            "behaviorHints": {
                "proxyHeaders": {
                    "request": {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                        "Referer": "https://yanhh3d.run/"
                    }
                }
            }
        })

    # Look for iframes
    iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html)
    for idx, if_url in enumerate(iframes, 1):
        if not if_url.startswith("http"):
            if_url = f"https:{if_url}" if if_url.startswith("//") else f"{YANHH3D_BASE}{if_url}"
        streams.append({
            "name": f"🌐 Yanhh3d Web Player #{idx}",
            "title": f"Web Embed Server #{idx}",
            "externalUrl": if_url
        })

    if not streams:
        streams.append({
            "name": "🌐 Yanhh3d Web",
            "title": "Mở trang xem tập trên Yanhh3d",
            "externalUrl": url
        })

    return {"streams": streams}

# ------------------------------------------------------------------
# Search Helper for Dashboard
# ------------------------------------------------------------------
async def search_yanhh3d(query: str, max_results: int = 15) -> List[Dict[str, Any]]:
    results = []
    try:
        url = f"{YANHH3D_BASE}/search?keysearch={urllib.parse.quote(query)}"
        html = await yanhh_fetch_html(url)
        metas = parse_yanhh_cards(html)
        results = metas[:max_results]
    except Exception as e:
        logger.warning(f"Yanhh3d search error: {e}")
    return results
