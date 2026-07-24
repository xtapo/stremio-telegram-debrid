from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse, Response
import httpx
import urllib.parse
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

vsmov_router = APIRouter(prefix="", tags=["vsmov"])

VSMOV_API_BASE = "https://vsmov.com/api"

# ------------------------------------------------------------------
# Manifest
# ------------------------------------------------------------------
VSMOV_GENRES_MAP = {
    "Hành Động": "hanh-dong",
    "Tình Cảm": "tinh-cam",
    "Hài": "hai",
    "Phim Hài": "hai",
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
    "Phim Nhạc": "am-nhac",
    "Phim 18+": "phim-18"
}

VSMOV_COUNTRIES_MAP = {
    "Trung Quốc": "trung-quoc",
    "Hàn Quốc": "han-quoc",
    "Mỹ": "my",
    "Âu Mỹ": "au-my",
    "Nhật Bản": "nhat-ban",
    "Thái Lan": "thai-lan",
    "Hồng Kông": "hong-kong",
    "Đài Loan": "dai-loan",
    "Việt Nam": "viet-nam",
    "Ấn Độ": "an-do",
    "Anh": "anh",
    "Pháp": "phap",
    "Đức": "duc",
    "Nga": "nga"
}

GENRE_OPTIONS = list(VSMOV_GENRES_MAP.keys())
COUNTRY_OPTIONS = list(VSMOV_COUNTRIES_MAP.keys())
ALL_FILTER_OPTIONS = GENRE_OPTIONS + COUNTRY_OPTIONS

MANIFEST = {
    "id": "com.stremio.vsmov.addon",
    "version": "1.0.0",
    "name": "VSMov - Phim Miễn Phí",
    "description": "Xem phim Việt Nam miễn phí từ VSMov (HLS HD Trực Tiếp)",
    "resources": [
        "catalog",
        {
            "name": "meta",
            "types": ["movie", "series"],
            "idPrefixes": ["vsmov:"]
        },
        {
            "name": "stream",
            "types": ["movie", "series"],
            "idPrefixes": ["vsmov:"]
        }
    ],
    "types": ["movie", "series"],
    "catalogs": [
        {
            "type": "movie",
            "id": "vsmov_phim_moi",
            "name": "VSMov - Phim Mới Cập Nhật",
            "extra": [
                {"name": "genre", "options": ALL_FILTER_OPTIONS, "isRequired": False},
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        },
        {
            "type": "movie",
            "id": "vsmov_the_loai",
            "name": "VSMov - Phim Theo Thể Loại",
            "extra": [
                {"name": "genre", "options": GENRE_OPTIONS, "isRequired": False},
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        },
        {
            "type": "movie",
            "id": "vsmov_quoc_gia",
            "name": "VSMov - Phim Theo Quốc Gia",
            "extra": [
                {"name": "genre", "options": COUNTRY_OPTIONS, "isRequired": False},
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        },
        {
            "type": "series",
            "id": "vsmov_phim_moi_series",
            "name": "VSMov - Phim Mới Cập Nhật",
            "extra": [
                {"name": "genre", "options": ALL_FILTER_OPTIONS, "isRequired": False},
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        },
        {
            "type": "series",
            "id": "vsmov_the_loai_series",
            "name": "VSMov - Phim Theo Thể Loại",
            "extra": [
                {"name": "genre", "options": GENRE_OPTIONS, "isRequired": False},
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        },
        {
            "type": "series",
            "id": "vsmov_quoc_gia_series",
            "name": "VSMov - Phim Theo Quốc Gia",
            "extra": [
                {"name": "genre", "options": COUNTRY_OPTIONS, "isRequired": False},
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        },
        {
            "type": "series",
            "id": "vsmov_trung_quoc",
            "name": "VSMov - Phim Trung Quốc",
            "extra": [
                {"name": "skip", "isRequired": False}
            ]
        },
        {
            "type": "series",
            "id": "vsmov_han_quoc",
            "name": "VSMov - Phim Hàn Quốc",
            "extra": [
                {"name": "skip", "isRequired": False}
            ]
        },
        {
            "type": "movie",
            "id": "vsmov_au_my",
            "name": "VSMov - Phim Âu Mỹ",
            "extra": [
                {"name": "skip", "isRequired": False}
            ]
        }
    ]
}

@vsmov_router.get("/vsmov/manifest.json")
@vsmov_router.get("/manifest.json")
async def get_manifest():
    return JSONResponse(MANIFEST)

# ------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------
def extract_m3u8_url(embed_url: str) -> str:
    """Extract direct master.m3u8 URL from VSMov embed link."""
    if not embed_url:
        return ""
    if embed_url.endswith(".m3u8"):
        return embed_url
    
    # Example embed_url: https://v13.streamvsmov.com/video/7fdbf8da-4b58-46ff-a2db-b1f449d4b8f8
    match = re.search(r'https?://([^/]+)/video/([^/?#]+)', embed_url)
    if match:
        domain = match.group(1)
        video_hash = match.group(2)
        return f"https://{domain}/stream/{video_hash}/master.m3u8"
    
    return embed_url

def rewrite_m3u8_playlist(m3u8_text: str, base_m3u8_url: str, referer: str, proxy_endpoint_url: str) -> str:
    """Rewrite URLs in m3u8 playlist to route through stream_proxy."""
    lines = m3u8_text.splitlines()
    new_lines = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('#'):
            if 'URI="' in stripped:
                def replace_uri(match):
                    uri = match.group(1)
                    full_uri = urllib.parse.urljoin(base_m3u8_url, uri)
                    proxied = f"{proxy_endpoint_url}?url={urllib.parse.quote(full_uri, safe='')}&referer={urllib.parse.quote(referer, safe='')}"
                    return f'URI="{proxied}"'
                stripped = re.sub(r'URI="([^"]+)"', replace_uri, stripped)
            new_lines.append(stripped)
        else:
            full_segment_url = urllib.parse.urljoin(base_m3u8_url, stripped)
            proxied_segment_url = f"{proxy_endpoint_url}?url={urllib.parse.quote(full_segment_url, safe='')}&referer={urllib.parse.quote(referer, safe='')}"
            new_lines.append(proxied_segment_url)
            
    return "\n".join(new_lines)

def strip_fake_png_header(content: bytes) -> bytes:
    """Strip fake PNG container header from VSMov TS video segments."""
    if not content.startswith(b"\x89PNG"):
        return content
    pos = 0
    while True:
        pos = content.find(b'G', pos)
        if pos == -1 or pos > 2048:
            break
        if pos + 188 < len(content) and content[pos + 188] == 0x47:
            if pos + 376 < len(content) and content[pos + 376] == 0x47:
                return content[pos:]
        pos += 1
    return content

# ------------------------------------------------------------------
# Stream Proxy
# ------------------------------------------------------------------
@vsmov_router.get("/vsmov/stream_proxy")
@vsmov_router.get("/stream_proxy")
async def vsmov_stream_proxy(request: Request, url: str, referer: Optional[str] = None):
    """Proxy video streams with correct User-Agent and Referer headers for Stremio Player."""
    if not url:
        raise HTTPException(status_code=400, detail="Missing stream URL")
    
    if " " in url:
        url = url.replace(" ", "+")
        
    ref = referer or "https://vsmov.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": ref
    }

    base_url = str(request.base_url).rstrip("/")
    proxy_endpoint = f"{base_url}/vsmov/stream_proxy" if not base_url.endswith("/vsmov") else f"{base_url}/stream_proxy"

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            content_type = resp.headers.get("Content-Type", "application/vnd.apple.mpegurl")
            
            if "#EXTM3U" in resp.text:
                rewritten_m3u8 = rewrite_m3u8_playlist(resp.text, url, ref, proxy_endpoint)
                return Response(content=rewritten_m3u8, status_code=200, media_type="application/vnd.apple.mpegurl")

            raw_bytes = resp.content
            clean_bytes = strip_fake_png_header(raw_bytes)
            media_type = "video/mp2t" if clean_bytes != raw_bytes else content_type

            return Response(content=clean_bytes, status_code=resp.status_code, media_type=media_type)
    except Exception as e:
        logger.error(f"VSMov stream proxy error for {url}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Catalog Handler
# ------------------------------------------------------------------
@vsmov_router.get("/vsmov/catalog/{type}/{id}.json")
@vsmov_router.get("/vsmov/catalog/{type}/{id}/{extra}.json")
@vsmov_router.get("/catalog/{type}/{id}.json")
@vsmov_router.get("/catalog/{type}/{id}/{extra}.json")
async def vsmov_catalog_handler(request: Request, type: str, id: str, extra: Optional[str] = None):
    search_query = None
    genre_query = None
    skip = 0

    if extra:
        params = urllib.parse.parse_qs(extra)
        if "search" in params:
            search_query = params["search"][0]
        if "genre" in params:
            genre_query = params["genre"][0]
        if "skip" in params and params["skip"][0].isdigit():
            skip = int(params["skip"][0])

    page = (skip // 24) + 1

    if search_query:
        api_url = f"{VSMOV_API_BASE}/tim-kiem?keyword={urllib.parse.quote(search_query)}"
    elif genre_query:
        if genre_query in VSMOV_GENRES_MAP:
            genre_slug = VSMOV_GENRES_MAP[genre_query]
            api_url = f"{VSMOV_API_BASE}/the-loai/{genre_slug}?page={page}"
        elif genre_query in VSMOV_COUNTRIES_MAP:
            country_slug = VSMOV_COUNTRIES_MAP[genre_query]
            api_url = f"{VSMOV_API_BASE}/quoc-gia/{country_slug}?page={page}"
        else:
            api_url = f"{VSMOV_API_BASE}/the-loai/{genre_query.lower()}?page={page}"
    elif id in ["vsmov_trung_quoc"]:
        api_url = f"{VSMOV_API_BASE}/quoc-gia/trung-quoc?page={page}"
    elif id in ["vsmov_han_quoc"]:
        api_url = f"{VSMOV_API_BASE}/quoc-gia/han-quoc?page={page}"
    elif id in ["vsmov_au_my"]:
        api_url = f"{VSMOV_API_BASE}/quoc-gia/au-my?page={page}"
    elif id in ["vsmov_the_loai", "vsmov_the_loai_series"]:
        api_url = f"{VSMOV_API_BASE}/the-loai/hanh-dong?page={page}"
    elif id in ["vsmov_quoc-gia", "vsmov_quoc_gia_series"]:
        api_url = f"{VSMOV_API_BASE}/quoc-gia/trung-quoc?page={page}"
    else:
        api_url = f"{VSMOV_API_BASE}/danh-sach/phim-moi-cap-nhat?page={page}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(api_url, headers=headers)
            if res.status_code != 200:
                return {"metas": []}
            data = res.json()
            items = data.get("items", [])

            metas = []
            for item in items:
                slug = item.get("slug")
                if not slug:
                    continue
                
                poster = item.get("thumb_url") or item.get("poster_url") or ""
                if poster and not poster.startswith("http"):
                    poster = f"https://vsmov.com{poster}" if poster.startswith("/") else f"https://vsmov.com/{poster}"

                metas.append({
                    "id": f"vsmov:{slug}",
                    "type": type,
                    "name": item.get("name", "Unknown"),
                    "poster": poster,
                    "description": f"Chất lượng: {item.get('quality', 'HD')} | Tập: {item.get('episode_current', 'Full')}"
                })

            return {"metas": metas}
    except Exception as e:
        logger.error(f"Error fetching VSMov catalog: {e}")
        return {"metas": []}

# ------------------------------------------------------------------
# Meta Handler
# ------------------------------------------------------------------
@vsmov_router.get("/vsmov/meta/{type}/{id}.json")
@vsmov_router.get("/meta/{type}/{id}.json")
async def vsmov_meta_handler(type: str, id: str):
    slug = id.replace("vsmov:", "")
    api_url = f"{VSMOV_API_BASE}/phim/{slug}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(api_url, headers=headers)
            if res.status_code != 200:
                return {"meta": {}}
            data = res.json()
            movie = data.get("movie")
            if not movie:
                return {"meta": {}}

            poster = movie.get("thumb_url") or movie.get("poster_url") or ""
            if poster and not poster.startswith("http"):
                poster = f"https://vsmov.com{poster}" if poster.startswith("/") else f"https://vsmov.com/{poster}"

            backdrop = movie.get("poster_url") or poster

            genres = [g.get("name") for g in movie.get("category", []) if isinstance(g, dict)]

            created_data = movie.get("created")
            if isinstance(created_data, dict):
                created_str = created_data.get("time", "")
            else:
                created_str = str(created_data) if created_data else ""

            episodes_data = data.get("episodes", [])
            videos = []

            for s_idx, server in enumerate(episodes_data):
                server_name = server.get("server_name", f"Server #{s_idx + 1}")
                items = server.get("server_data", []) or server.get("items", [])

                for ep in items:
                    ep_name = ep.get("name", "1")
                    ep_slug = ep.get("slug", f"tap-{ep_name}")
                    
                    ep_num = 1
                    ep_num_match = re.search(r'\d+', ep_name)
                    if ep_num_match:
                        ep_num = int(ep_num_match.group(0))

                    videos.append({
                        "id": f"vsmov:{slug}:{s_idx}:{ep_slug}",
                        "title": f"Tập {ep_name} [{server_name}]",
                        "season": 1,
                        "episode": ep_num,
                        "released": created_str
                    })


            is_series = len(videos) > 1 or movie.get("type") in ["hoathinh", "series", "tvshows"] or type == "series"

            meta = {
                "id": f"vsmov:{slug}",
                "type": type,
                "name": movie.get("name", "Unknown"),
                "poster": poster,
                "background": backdrop,
                "description": movie.get("content", "").replace("<p>", "").replace("</p>", "").replace("\r\n", " "),
                "genres": genres,
                "releaseInfo": str(movie.get("year", "")),
                "videos": videos if is_series else []
            }

            return {"meta": meta}

    except Exception as e:
        logger.error(f"Error fetching VSMov meta for {id}: {e}")
        return {"meta": {}}

# ------------------------------------------------------------------
# Stream Handler
# ------------------------------------------------------------------
@vsmov_router.get("/vsmov/stream/{type}/{id}.json")
@vsmov_router.get("/stream/{type}/{id}.json")
async def vsmov_stream_handler(request: Request, type: str, id: str):
    parts = id.split(":")
    slug = parts[1] if len(parts) > 1 else id
    target_ep_slug = parts[3] if len(parts) > 3 else (parts[2] if len(parts) > 2 and not parts[2].isdigit() else None)

    api_url = f"{VSMOV_API_BASE}/phim/{slug}"

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(api_url)
            if res.status_code != 200:
                return {"streams": []}
            data = res.json()
            movie = data.get("movie")
            if not movie:
                return {"streams": []}

            episodes_data = data.get("episodes", [])
            streams = []

            base_url = str(request.base_url).rstrip("/")
            movie_name = movie.get("name", "")
            quality = movie.get("quality", "HD")

            for s_idx, server in enumerate(episodes_data):
                server_name = server.get("server_name", f"Server #{s_idx + 1}").strip()
                items = server.get("server_data", []) or server.get("items", [])

                target_item = None
                if target_ep_slug:
                    for item in items:
                        if item.get("slug") == target_ep_slug:
                            target_item = item
                            break
                if not target_item and items:
                    target_item = items[0]

                if target_item:
                    embed_url = target_item.get("link_embed") or target_item.get("embed") or ""
                    m3u8_direct = target_item.get("link_m3u8") or extract_m3u8_url(embed_url)
                    ep_title = target_item.get("name", "")
                    
                    if m3u8_direct:
                        proxy_stream_url = f"{base_url}/vsmov/stream_proxy?url={urllib.parse.quote(m3u8_direct, safe='')}&referer={urllib.parse.quote(embed_url or 'https://vsmov.com/', safe='')}"
                        
                        # 1. Native Stremio Internal Video Player (PRIMARY - 100% HLS Playback Success)
                        streams.append({
                            "name": f"VSMov Proxy [{server_name}]",
                            "title": f"▶ Phát Trực Tiếp trong Stremio [{server_name}] - Tập {ep_title}\n🎬 {movie_name}\n⚡ {quality} | HLS HD Mượt Mà\n⚡ Trình phát mặc định Stremio (LibVLC/ExoPlayer)",
                            "url": proxy_stream_url,
                            "behaviorHints": {
                                "notSupported": False,
                                "requestHeaders": {
                                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                                    "Referer": embed_url or "https://vsmov.com/"
                                }
                            }
                        })

                        # 2. Direct HLS Stream
                        streams.append({
                            "name": f"VSMov Direct [{server_name}]",
                            "title": f"⚡ Direct HLS Stream [{server_name}] - Tập {ep_title}",
                            "url": m3u8_direct,
                            "behaviorHints": {
                                "notSupported": False,
                                "requestHeaders": {
                                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                                    "Referer": embed_url or "https://vsmov.com/"
                                }
                            }
                        })

                    if embed_url:
                        streams.append({
                            "name": f"VSMov Web [{server_name}]",
                            "title": f"🌐 Mở Trình Duyệt Web [{server_name}] - Tập {ep_title}",
                            "externalUrl": embed_url
                        })

            return {"streams": streams}
    except Exception as e:
        logger.error(f"Error fetching VSMov streams for {id}: {e}")
        return {"streams": []}
