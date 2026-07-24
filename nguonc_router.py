import logging
import urllib.parse
import re
import base64
import json
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse, Response


import httpx

logger = logging.getLogger("nguonc_addon")

nguonc_router = APIRouter()

NGUONC_API_BASE = "https://phim.nguonc.com/api"

GENRES_MAP = {
    "Hành Động": "hanh-dong",
    "Phiêu Lưu": "phieu-luu",
    "Hoạt Hình": "hoat-hinh",
    "Hài": "phim-hai",
    "Phim Hài": "phim-hai",
    "Hình Sự": "hinh-su",
    "Tài Liệu": "tai-lieu",
    "Chính Kịch": "chinh-kich",
    "Gia Đình": "gia-dinh",
    "Giả Tưởng": "gia-tuong",
    "Lịch Sử": "lich-su",
    "Kinh Dị": "kinh-di",
    "Nhạc": "phim-nhac",
    "Phim Nhạc": "phim-nhac",
    "Bí Ẩn": "bi-an",
    "Lãng Mạn": "lang-man",
    "Khoa Học Viễn Tưởng": "khoa-hoc-vien-tuong",
    "Gây Cấn": "gay-can",
    "Chiến Tranh": "chien-tranh",
    "Tâm Lý": "tam-ly",
    "Tình Cảm": "tinh-cam",
    "Cổ Trang": "co-trang",
    "Miền Tây": "mien-tay",
    "Phim 18+": "phim-18"
}

COUNTRIES_MAP = {
    "Âu Mỹ": "au-my",
    "Anh": "anh",
    "Trung Quốc": "trung-quoc",
    "Indonesia": "indonesia",
    "Việt Nam": "viet-nam",
    "Pháp": "phap",
    "Hồng Kông": "hong-kong",
    "Hàn Quốc": "han-quoc",
    "Nhật Bản": "nhat-ban",
    "Thái Lan": "thai-lan",
    "Đài Loan": "dai-loan",
    "Nga": "nga",
    "Hà Lan": "ha-lan",
    "Philippines": "philippines",
    "Ấn Độ": "an-do",
    "Quốc gia khác": "quoc-gia-khac"
}

YEARS_LIST = [str(y) for y in range(2026, 2003, -1)]

GENRE_OPTIONS = ["Hành Động", "Phiêu Lưu", "Hoạt Hình", "Phim Hài", "Hình Sự", "Tài Liệu", "Chính Kịch", "Gia Đình", "Giả Tưởng", "Lịch Sử", "Kinh Dị", "Phim Nhạc", "Bí Ẩn", "Lãng Mạn", "Khoa Học Viễn Tưởng", "Gây Cấn", "Chiến Tranh", "Tâm Lý", "Tình Cảm", "Cổ Trang", "Miền Tây", "Phim 18+"]
COUNTRY_OPTIONS = list(COUNTRIES_MAP.keys())
YEAR_OPTIONS = YEARS_LIST

ALL_FILTER_OPTIONS = GENRE_OPTIONS + COUNTRY_OPTIONS + YEAR_OPTIONS

async def extract_m3u8_from_embed(embed_url: str) -> str:
    """Extract direct m3u8 playlist URL from streamc embed page."""
    if not embed_url:
        return ""
    try:
        parsed = urllib.parse.urlparse(embed_url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://phim.nguonc.com/'
            }
            resp = await client.get(embed_url, headers=headers)
            if resp.status_code == 200:
                html = resp.text
                obf_match = re.search(r'data-obf="([^"]+)"', html)
                if obf_match:
                    obf = obf_match.group(1)
                    d1 = json.loads(base64.b64decode(obf).decode('utf-8'))
                    sub_str = d1.get('sUb')
                    if sub_str:
                        return f"{domain}/{sub_str}?d=1"
    except Exception as e:
        logger.warning(f"Error extracting m3u8 from embed ({embed_url}): {e}")
    return embed_url

def parse_movie_type(item: Dict[str, Any]) -> str:
    """Determine if movie or series based on NguonC category or total_episodes."""
    cat = item.get("category", {})
    if isinstance(cat, dict):
        for v in cat.values():
            if isinstance(v, dict):
                group_list = v.get("list", [])
                for g in group_list:
                    name = g.get("name", "").lower()
                    if "phim lẻ" in name or "phim le" in name:
                        return "movie"
                    if "phim bộ" in name or "phim bo" in name or "tv shows" in name:
                        return "series"
    total_ep = str(item.get("total_episodes", "1")).lower()
    if total_ep in ["1", "full", "1 tập", "1/1"]:
        return "movie"
    return "series"

def parse_genres(item: Dict[str, Any]) -> List[str]:
    """Extract genre names from category object."""
    genres = []
    cat = item.get("category", {})
    if isinstance(cat, dict):
        for v in cat.values():
            if isinstance(v, dict):
                group_info = v.get("group", {})
                if group_info.get("name") in ["Thể loại", "Genre"]:
                    for g in v.get("list", []):
                        if g.get("name"):
                            genres.append(g["name"])
    return genres

def item_to_stremio_meta(item: Dict[str, Any]) -> Dict[str, Any]:
    """Convert NguonC movie item to Stremio Meta object."""
    slug = item.get("slug", "")
    m_type = parse_movie_type(item)
    
    # Extract year if possible
    year = None
    created = item.get("created", "")
    if created and len(created) >= 4:
        try:
            year = int(created[:4])
        except ValueError:
            pass
            
    poster = item.get("poster_url") or item.get("thumb_url") or ""
    thumb = item.get("thumb_url") or poster
    
    description = item.get("description") or ""
    orig_name = item.get("original_name")
    quality = item.get("quality")
    lang = item.get("language")
    
    extra_details = []
    if orig_name:
        extra_details.append(f"Tên gốc: {orig_name}")
    if quality:
        extra_details.append(f"Chất lượng: {quality}")
    if lang:
        extra_details.append(f"Ngôn ngữ: {lang}")
        
    if extra_details:
        prefix = " | ".join(extra_details)
        description = f"{prefix}\n\n{description}".strip()

    return {
        "id": f"nguonc:{slug}",
        "type": m_type,
        "name": item.get("name", "Phim NguonC"),
        "poster": poster,
        "posterShape": "poster",
        "banner": poster,
        "background": poster,
        "description": description,
        "genres": parse_genres(item),
        "releaseInfo": str(year) if year else None
    }

def get_nguonc_manifest(request: Request) -> Dict[str, Any]:
    base_url = str(request.base_url).rstrip("/")
    return {
        "id": "com.stremio.nguonc.phim",
        "version": "1.0.0",
        "name": "NguonC Phim (Cinema)",
        "description": "Xem trực tuyến Phim Lẻ, Phim Bộ, TV Shows, Hoạt Hình Vietsub / Thuyết Minh từ NguonC API.",
        "logo": "https://phim.nguonc.com/public/images/logo.png",
        "resources": ["catalog", "meta", "stream"],
        "types": ["movie", "series"],
        "catalogs": [
            {
                "type": "movie",
                "id": "nguonc_phim_moi_movie",
                "name": "NguonC - Phim Mới Cập Nhật",
                "extra": [
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False}
                ]
            },
            {
                "type": "movie",
                "id": "nguonc_phim_le",
                "name": "NguonC - Phim Lẻ",
                "extra": [
                    {"name": "genre", "isRequired": False, "options": ALL_FILTER_OPTIONS},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False}
                ]
            },
            {
                "type": "movie",
                "id": "nguonc_the_loai",
                "name": "NguonC - Phim Theo Thể Loại",
                "extra": [
                    {"name": "genre", "isRequired": False, "options": GENRE_OPTIONS},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False}
                ]
            },
            {
                "type": "movie",
                "id": "nguonc_quoc_gia",
                "name": "NguonC - Phim Theo Quốc Gia",
                "extra": [
                    {"name": "genre", "isRequired": False, "options": COUNTRY_OPTIONS},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False}
                ]
            },
            {
                "type": "movie",
                "id": "nguonc_nam",
                "name": "NguonC - Phim Theo Năm",
                "extra": [
                    {"name": "genre", "isRequired": False, "options": YEAR_OPTIONS},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False}
                ]
            },
            {
                "type": "series",
                "id": "nguonc_phim_moi_series",
                "name": "NguonC - Phim Mới Cập Nhật",
                "extra": [
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False}
                ]
            },
            {
                "type": "series",
                "id": "nguonc_phim_bo",
                "name": "NguonC - Phim Bộ",
                "extra": [
                    {"name": "genre", "isRequired": False, "options": ALL_FILTER_OPTIONS},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False}
                ]
            },
            {
                "type": "series",
                "id": "nguonc_dang_chieu",
                "name": "NguonC - Phim Đang Chiếu",
                "extra": [
                    {"name": "genre", "isRequired": False, "options": ALL_FILTER_OPTIONS},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False}
                ]
            },
            {
                "type": "series",
                "id": "nguonc_tv_shows",
                "name": "NguonC - TV Shows",
                "extra": [
                    {"name": "genre", "isRequired": False, "options": ALL_FILTER_OPTIONS},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False}
                ]
            },
            {
                "type": "series",
                "id": "nguonc_the_loai_series",
                "name": "NguonC - Phim Theo Thể Loại",
                "extra": [
                    {"name": "genre", "isRequired": False, "options": GENRE_OPTIONS},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False}
                ]
            },
            {
                "type": "series",
                "id": "nguonc_quoc_gia_series",
                "name": "NguonC - Phim Theo Quốc Gia",
                "extra": [
                    {"name": "genre", "isRequired": False, "options": COUNTRY_OPTIONS},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False}
                ]
            },
            {
                "type": "series",
                "id": "nguonc_nam_series",
                "name": "NguonC - Phim Theo Năm",
                "extra": [
                    {"name": "genre", "isRequired": False, "options": YEAR_OPTIONS},
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

@nguonc_router.api_route("/manifest.json", methods=["GET", "HEAD"])
@nguonc_router.api_route("/nguonc/manifest.json", methods=["GET", "HEAD"])
async def nguonc_manifest_endpoint(request: Request):
    return JSONResponse(get_nguonc_manifest(request))


@nguonc_router.get("/catalog/{type}/{catalog_id}.json")
@nguonc_router.get("/catalog/{type}/{catalog_id}/{extra}.json")
@nguonc_router.get("/nguonc/catalog/{type}/{catalog_id}.json")
@nguonc_router.get("/nguonc/catalog/{type}/{catalog_id}/{extra}.json")
async def nguonc_catalog_handler(type: str, catalog_id: str, extra: str = None):
    skip = 0
    search_query = None
    genre_query = None

    if extra:
        params = urllib.parse.parse_qs(extra)
        if "skip" in params:
            try:
                skip = int(params["skip"][0])
            except ValueError:
                pass
        if "search" in params:
            search_query = params["search"][0]
        if "genre" in params:
            genre_query = params["genre"][0]

    # Calculate NguonC page (10 items per page)
    page = (skip // 10) + 1

    api_url = ""
    if search_query:
        api_url = f"{NGUONC_API_BASE}/films/search?keyword={urllib.parse.quote(search_query)}&page={page}"
    elif genre_query:
        if genre_query in GENRES_MAP:
            slug = GENRES_MAP[genre_query]
            api_url = f"{NGUONC_API_BASE}/films/the-loai/{slug}?page={page}"
        elif genre_query in COUNTRIES_MAP:
            slug = COUNTRIES_MAP[genre_query]
            api_url = f"{NGUONC_API_BASE}/films/quoc-gia/{slug}?page={page}"
        elif genre_query.isdigit() and len(genre_query) == 4:
            api_url = f"{NGUONC_API_BASE}/films/nam-phat-hanh/{genre_query}?page={page}"
        else:
            api_url = f"{NGUONC_API_BASE}/films/phim-moi-cap-nhat?page={page}"
    else:
        if catalog_id in ["nguonc_phim_moi_movie", "nguonc_phim_moi", "nguonc_phim_moi_series"]:
            api_url = f"{NGUONC_API_BASE}/films/phim-moi-cap-nhat?page={page}"
        elif catalog_id == "nguonc_phim_le":
            api_url = f"{NGUONC_API_BASE}/films/danh-sach/phim-le?page={page}"
        elif catalog_id == "nguonc_phim_bo":
            api_url = f"{NGUONC_API_BASE}/films/danh-sach/phim-bo?page={page}"
        elif catalog_id == "nguonc_dang_chieu":
            api_url = f"{NGUONC_API_BASE}/films/danh-sach/dang-chieu?page={page}"
        elif catalog_id == "nguonc_tv_shows":
            api_url = f"{NGUONC_API_BASE}/films/danh-sach/tv-shows?page={page}"
        elif catalog_id in ["nguonc_the_loai", "nguonc_the_loai_series"]:
            api_url = f"{NGUONC_API_BASE}/films/the-loai/hanh-dong?page={page}"
        elif catalog_id in ["nguonc_quoc_gia", "nguonc_quoc_gia_series"]:
            api_url = f"{NGUONC_API_BASE}/films/quoc-gia/au-my?page={page}"
        elif catalog_id in ["nguonc_nam", "nguonc_nam_series"]:
            api_url = f"{NGUONC_API_BASE}/films/nam-phat-hanh/2026?page={page}"
        else:
            api_url = f"{NGUONC_API_BASE}/films/phim-moi-cap-nhat?page={page}"

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(api_url)
            if res.status_code != 200:
                return {"metas": []}
            data = res.json()
            items = data.get("items", [])
            metas = []
            for item in items:
                m = item_to_stremio_meta(item)
                # Filter type if needed
                if type == "movie" and m["type"] != "movie":
                    continue
                if type == "series" and m["type"] != "series":
                    continue
                metas.append(m)
            return {"metas": metas}
    except Exception as e:
        logger.error(f"Error fetching catalog {catalog_id}: {e}")
        return {"metas": []}

@nguonc_router.get("/meta/{type}/{id}.json")
@nguonc_router.get("/nguonc/meta/{type}/{id}.json")
async def nguonc_meta_handler(type: str, id: str):
    if id.startswith("vsmov:"):
        from vsmov_router import vsmov_meta_handler
        return await vsmov_meta_handler(type, id)

    slug = id.replace("nguonc:", "")
    api_url = f"{NGUONC_API_BASE}/film/{slug}"


    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(api_url)
            if res.status_code != 200:
                return {"meta": {}}
            data = res.json()
            movie = data.get("movie")
            if not movie:
                return {"meta": {}}

            meta = item_to_stremio_meta(movie)
            
            # Cast & Director
            casts = movie.get("casts")
            if isinstance(casts, str) and casts.strip():
                meta["cast"] = [c.strip() for c in casts.split(",") if c.strip()]
            director = movie.get("director")
            if isinstance(director, str) and director.strip():
                meta["director"] = [d.strip() for d in director.split(",") if d.strip()]

            # Handle Series Videos (Episodes)
            episodes_data = movie.get("episodes", [])
            if meta["type"] == "series" and episodes_data:
                videos = []
                # Use primary server (index 0) for season 1 episode structure
                primary_server = episodes_data[0]
                ep_items = primary_server.get("items", [])
                
                for idx, ep_item in enumerate(ep_items, 1):
                    ep_name = ep_item.get("name", str(idx))
                    ep_slug = ep_item.get("slug", f"tap-{idx}")
                    
                    # Video ID format: nguonc:{slug}:0:{ep_slug}
                    videos.append({
                        "id": f"nguonc:{slug}:0:{ep_slug}",
                        "title": f"Tập {ep_name}",
                        "season": 1,
                        "episode": idx,
                        "released": movie.get("modified") or movie.get("created")
                    })
                meta["videos"] = videos

            return {"meta": meta}
    except Exception as e:
        logger.error(f"Error fetching meta for {id}: {e}")
        return {"meta": {}}

def rewrite_m3u8_playlist(m3u8_text: str, base_m3u8_url: str, referer: str, proxy_endpoint_url: str) -> str:
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

@nguonc_router.get("/stream_proxy")
@nguonc_router.get("/nguonc/stream_proxy")
async def nguonc_stream_proxy(request: Request, url: str, referer: Optional[str] = None):
    """Proxy video streams with correct User-Agent and Referer headers for Stremio Player."""
    if not url:
        raise HTTPException(status_code=400, detail="Missing stream URL")
    
    # Restore space to + if query string decoding converted + to space
    if " " in url:
        url = url.replace(" ", "+")
        
    ref = referer or "https://phim.nguonc.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": ref
    }

    base_url = str(request.base_url).rstrip("/")
    proxy_endpoint = f"{base_url}/nguonc/stream_proxy" if not base_url.endswith("/nguonc") else f"{base_url}/stream_proxy"

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            content_type = resp.headers.get("Content-Type", "application/vnd.apple.mpegurl")
            
            if "#EXTM3U" in resp.text:
                rewritten_m3u8 = rewrite_m3u8_playlist(resp.text, url, ref, proxy_endpoint)
                return Response(content=rewritten_m3u8, status_code=200, media_type="application/vnd.apple.mpegurl")

            return Response(content=resp.content, status_code=resp.status_code, media_type=content_type)
    except Exception as e:
        logger.error(f"Stream proxy error for {url}: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@nguonc_router.get("/player", response_class=HTMLResponse)
@nguonc_router.get("/nguonc/player", response_class=HTMLResponse)
async def nguonc_player_page(url: str):
    """Clean full-screen HTML5 Web Player wrapper for NguonC embed streams."""
    if not url:
        raise HTTPException(status_code=400, detail="Missing embed URL")
    
    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NguonC Cinema Player</title>
    <style>
        html, body {{
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            background-color: #000;
            overflow: hidden;
        }}
        iframe {{
            width: 100%;
            height: 100%;
            border: none;
        }}
    </style>
</head>
<body>
    <iframe src="{url}" allowfullscreen allow="autoplay; encrypted-media; picture-in-picture"></iframe>
</body>
</html>
"""
    return HTMLResponse(content=html)

@nguonc_router.get("/stream/{type}/{id}.json")
@nguonc_router.get("/nguonc/stream/{type}/{id}.json")
async def nguonc_stream_handler(request: Request, type: str, id: str):
    if id.startswith("vsmov:"):
        from vsmov_router import vsmov_stream_handler
        return await vsmov_stream_handler(request, type, id)

    parts = id.split(":")
    slug = parts[1] if len(parts) > 1 else id

    target_ep_slug = parts[3] if len(parts) > 3 else (parts[2] if len(parts) > 2 and not parts[2].isdigit() else None)

    api_url = f"{NGUONC_API_BASE}/film/{slug}"

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(api_url)
            if res.status_code != 200:
                return {"streams": []}
            data = res.json()
            movie = data.get("movie")
            if not movie:
                return {"streams": []}

            episodes_data = movie.get("episodes", [])
            streams = []

            base_url = str(request.base_url).rstrip("/")
            movie_name = movie.get("name", "")
            quality = movie.get("quality", "HD")
            lang = movie.get("language", "Vietsub")

            # Iterate ALL servers to ensure complete server/episode links
            for s_idx, server in enumerate(episodes_data):
                server_name = server.get("server_name", f"Server #{s_idx + 1}")
                items = server.get("items", [])

                # Find episode item matching target_ep_slug or default to first
                target_item = None
                if target_ep_slug:
                    for item in items:
                        if item.get("slug") == target_ep_slug:
                            target_item = item
                            break
                if not target_item and items:
                    target_item = items[0]

                if target_item:
                    embed_url = target_item.get("embed", "")
                    ep_title = target_item.get("name", "")
                    
                    if embed_url:
                        # Extract direct sUb M3U8 stream URL
                        m3u8_url = await extract_m3u8_from_embed(embed_url)
                        
                        # Direct Python Proxy Stream URL for native internal Stremio player
                        proxy_stream_url = f"{base_url}/nguonc/stream_proxy?url={urllib.parse.quote(m3u8_url, safe='')}&referer={urllib.parse.quote(embed_url, safe='')}"
                        
                        # 1. Native Stremio Internal Video Player (PRIMARY - url property)
                        streams.append({
                            "name": f"NguonC Proxy [{server_name}]",
                            "title": f"▶ Phát Trực Tiếp Trong Stremio [{server_name}] - Tập {ep_title}\n🎬 {movie_name}\n⚡ {quality} | {lang}\n⚡ Trình phát mặc định Stremio (VLC/ExoPlayer)",
                            "url": proxy_stream_url,
                            "behaviorHints": {
                                "notSupported": False,
                                "requestHeaders": {
                                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                                    "Referer": embed_url
                                }
                            }
                        })

                        # 2. Direct HLS Stream (Fallback)
                        if m3u8_url and m3u8_url != embed_url:
                            streams.append({
                                "name": f"NguonC Direct [{server_name}]",
                                "title": f"⚡ Direct HLS Stream [{server_name}] - Tập {ep_title}",
                                "url": m3u8_url,
                                "behaviorHints": {
                                    "notSupported": False,
                                    "requestHeaders": {
                                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                                        "Referer": embed_url
                                    }
                                }
                            })

                        # 3. External Web Player (Embed Backup)
                        streams.append({
                            "name": f"NguonC Web [{server_name}]",
                            "title": f"🌐 Mở Trình Duyệt Web [{server_name}] - Tập {ep_title}",
                            "externalUrl": embed_url
                        })

            return {"streams": streams}
    except Exception as e:
        logger.error(f"Error fetching streams for {id}: {e}")
        return {"streams": []}






@nguonc_router.get("/", response_class=HTMLResponse)
@nguonc_router.get("/nguonc", response_class=HTMLResponse)
@nguonc_router.get("/configure", response_class=HTMLResponse)
@nguonc_router.get("/nguonc/configure", response_class=HTMLResponse)
async def nguonc_landing_page(request: Request):

    base_url = str(request.base_url).rstrip("/")
    if request.url.path.startswith("/nguonc"):
        manifest_url = f"{base_url}/nguonc/manifest.json"
    else:
        manifest_url = f"{base_url}/manifest.json"

    stremio_protocol_url = manifest_url.replace("https://", "stremio://").replace("http://", "stremio://")
    web_stremio_url = f"https://web.stremio.com/#/addons?addon={urllib.parse.quote(manifest_url)}"

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NguonC Cinema - Stremio Addon</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
            color: #f8fafc;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .container {{
            background: rgba(30, 41, 59, 0.7);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 24px;
            padding: 40px;
            max-width: 600px;
            width: 100%;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            text-align: center;
        }}
        .logo {{
            width: 80px;
            height: 80px;
            margin-bottom: 20px;
            border-radius: 20px;
            box-shadow: 0 10px 25px rgba(99, 102, 241, 0.4);
        }}
        h1 {{
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 8px;
            background: linear-gradient(to right, #818cf8, #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        p.subtitle {{
            color: #94a3b8;
            font-size: 0.95rem;
            margin-bottom: 30px;
        }}
        .url-box {{
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 12px;
            padding: 14px 16px;
            font-family: monospace;
            font-size: 0.9rem;
            color: #38bdf8;
            width: 100%;
            margin-bottom: 20px;
            word-break: break-all;
        }}
        .btn-group {{
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-bottom: 30px;
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 14px 24px;
            border-radius: 12px;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.2s ease;
            cursor: pointer;
            border: none;
            font-size: 1rem;
        }}
        .btn-primary {{
            background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
            color: white;
            box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
        }}
        .btn-primary:hover {{
            opacity: 0.95;
            transform: translateY(-2px);
        }}
        .btn-secondary {{
            background: rgba(51, 65, 85, 0.8);
            color: #e2e8f0;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .btn-secondary:hover {{
            background: rgba(71, 85, 105, 1);
        }}
        .features {{
            text-align: left;
            background: rgba(15, 23, 42, 0.4);
            border-radius: 16px;
            padding: 20px;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }}
        .features h3 {{
            font-size: 1rem;
            margin-bottom: 12px;
            color: #cbd5e1;
        }}
        .features ul {{
            list-style: none;
        }}
        .features li {{
            font-size: 0.9rem;
            color: #94a3b8;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .features li::before {{
            content: "✓";
            color: #34d399;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="container">
        <img src="https://phim.nguonc.com/public/images/logo.png" alt="NguonC Logo" class="logo" onerror="this.src='https://stremio.com/website/stremio-logo-small.png'">
        <h1>NguonC Cinema Addon</h1>
        <p class="subtitle">Tích hợp trực tiếp toàn bộ kho phim NguonC API vào Stremio</p>
        
        <div class="url-box" id="manifestUrl">{manifest_url}</div>
        
        <div class="btn-group">
            <a href="{stremio_protocol_url}" class="btn btn-primary">🚀 Cài Đặt Vào Stremio App</a>
            <a href="{web_stremio_url}" target="_blank" class="btn btn-secondary">🌐 Cài Đặt Trên Stremio Web</a>
            <button onclick="copyManifestUrl()" class="btn btn-secondary" id="btnCopy">📋 Sao Chép Link Manifest</button>
        </div>

        <div class="features">
            <h3>✨ Tính năng nổi bật:</h3>
            <ul>
                <li>Danh mục Phim Lẻ, Phim Bộ, Đang Chiếu, TV Shows đầy đủ</li>
                <li>Lọc phim theo Thể Loại, Quốc Gia, Năm phát hành</li>
                <li>Tìm kiếm phim nhanh chóng trực tiếp từ Stremio</li>
                <li>Phát trực tiếp luồng HLS (.m3u8) sắc nét không giật lag</li>
            </ul>
        </div>
    </div>

    <script>
        function copyManifestUrl() {{
            const url = document.getElementById('manifestUrl').innerText;
            navigator.clipboard.writeText(url).then(() => {{
                const btn = document.getElementById('btnCopy');
                btn.innerText = '✅ Đã Sao Chép!';
                setTimeout(() => {{ btn.innerText = '📋 Sao Chép Link Manifest'; }}, 2000);
            }});
        }}
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html)

if __name__ == "__main__":
    import os
    import socket
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from vsmov_router import vsmov_router

    def get_lan_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip

    lan_ip = get_lan_ip()
    port = int(os.getenv("NGUONC_PORT", os.getenv("PORT", 7071)))
    
    print("\n" + "=" * 65)
    print(" 🚀 CINEMA STREMIO ADDONS STARTED SUCCESSFULLY!")
    print(f" 💻 Local PC Manifest:    http://127.0.0.1:{port}/vsmov/manifest.json")
    print(f" 📱 LAN Network Manifest:  http://{lan_ip}:{port}/vsmov/manifest.json")
    print(f" 🎬 NguonC LAN Manifest:   http://{lan_ip}:{port}/nguonc/manifest.json")
    print("=" * 65 + "\n")

    app = FastAPI(title="Cinema Stremio Addons")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(nguonc_router)
    app.include_router(vsmov_router, prefix="/vsmov")
    uvicorn.run(app, host="0.0.0.0", port=port)
