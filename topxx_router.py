from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse, Response
import httpx
import urllib.parse
import re
import logging
import unicodedata
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

topxx_router = APIRouter(prefix="", tags=["topxx"])

TOPXX_API_BASE = "https://topxx.vip/api/v1"

# ------------------------------------------------------------------
# Genres & Countries Pre-defined Options
# ------------------------------------------------------------------
GENRE_OPTIONS = [
    "Việt Sub", "Trung Quốc", "Hàn Quốc", "Nhật Bản", "Hentai 18+",
    "Không che", "Tập thể", "Âu Mỹ", "XNXX", "Sex 3D", "Hậu môn",
    "Chubby", "Vú to", "Sex Less", "Sex Gay", "Sex Nga", "Amateur",
    "Gangbang", "Sex Tự Quay", "4K"
]

COUNTRY_OPTIONS = [
    "Việt Nam", "Nhật Bản", "Mỹ", "Hàn Quốc", "Thái Lan", "Philippines",
    "Trung Quốc", "Đài Loan", "Hồng Kông", "Anh", "Pháp", "Đức", "Ý",
    "Tây Ban Nha", "Nga", "Hà Lan", "Séc", "Hungary", "Brazil", "Canada",
    "Úc", "Thụy Điển"
]

ALL_FILTER_OPTIONS = list(dict.fromkeys(GENRE_OPTIONS + COUNTRY_OPTIONS))

MANIFEST = {
    "id": "com.stremio.topxx.addon",
    "version": "1.0.1",
    "name": "TopXX - Phim 18+ Vietsub",
    "description": "Xem phim Adult 18+ Vietsub từ TopXX API (HLS HD Trực Tiếp)",
    "resources": [
        "catalog",
        {
            "name": "meta",
            "types": ["movie"],
            "idPrefixes": ["topxx:"]
        },
        {
            "name": "stream",
            "types": ["movie"],
            "idPrefixes": ["topxx:"]
        }
    ],
    "types": ["movie"],
    "catalogs": [
        {
            "type": "movie",
            "id": "topxx_phim_hom_nay",
            "name": "TopXX - Phim Đăng Hôm Nay (Today)",
            "extra": [
                {"name": "genre", "options": ALL_FILTER_OPTIONS, "isRequired": False},
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        },
        {
            "type": "movie",
            "id": "topxx_phim_moi",
            "name": "TopXX - Phim Mới Cập Nhật (Latest)",
            "extra": [
                {"name": "genre", "options": ALL_FILTER_OPTIONS, "isRequired": False},
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        },
        {
            "type": "movie",
            "id": "topxx_the_loai",
            "name": "TopXX - Thể Loại",
            "extra": [
                {"name": "genre", "options": GENRE_OPTIONS, "isRequired": False},
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        },
        {
            "type": "movie",
            "id": "topxx_quoc_gia",
            "name": "TopXX - Quốc Gia",
            "extra": [
                {"name": "genre", "options": COUNTRY_OPTIONS, "isRequired": False},
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        }
    ]
}

@topxx_router.get("/topxx/manifest.json")
@topxx_router.get("/manifest.json")
async def get_manifest():
    return JSONResponse(MANIFEST)

# Dynamic mapping caches: maps normalized key -> item code
GENRES_CACHE: Dict[str, str] = {}
COUNTRIES_CACHE: Dict[str, str] = {}

def normalize_key(text: str) -> str:
    """Normalize text for fuzzy matching (lowercase, strip accents & special chars)."""
    if not text:
        return ""
    text = text.lower().strip()
    # Normalize unicode to NFD and remove combining diacritics
    nfkd = unicodedata.normalize('NFD', text)
    stripped = "".join([c for c in nfkd if unicodedata.category(c) != 'Mn'])
    # Replace non-alphanumeric with empty space
    cleaned = re.sub(r'[^a-z0-9]', '', stripped)
    return cleaned

async def refresh_mappings():
    """Fetch genres and countries mappings from TopXX API and populate caches."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    async with httpx.AsyncClient(headers=headers, timeout=10.0, follow_redirects=True) as client:
        # Fetch Genres
        try:
            res = await client.get(f"{TOPXX_API_BASE}/genres")
            if res.status_code == 200:
                data = res.json().get("data", [])
                for item in data:
                    code = item.get("code")
                    slug = item.get("slug")
                    if code:
                        GENRES_CACHE[normalize_key(code)] = code
                        if slug:
                            GENRES_CACHE[normalize_key(slug)] = code
                        for t in item.get("translations", []):
                            name = t.get("name")
                            if name:
                                GENRES_CACHE[normalize_key(name)] = code
        except Exception as e:
            logger.error(f"Error fetching TopXX genres: {e}")

        # Fetch Countries
        try:
            res = await client.get(f"{TOPXX_API_BASE}/countries")
            if res.status_code == 200:
                data = res.json().get("data", [])
                for item in data:
                    code = item.get("code")
                    slug = item.get("slug")
                    if code:
                        COUNTRIES_CACHE[normalize_key(code)] = code
                        if slug:
                            COUNTRIES_CACHE[normalize_key(slug)] = code
                        for t in item.get("translations", []):
                            name = t.get("name")
                            if name:
                                COUNTRIES_CACHE[normalize_key(name)] = code
        except Exception as e:
            logger.error(f"Error fetching TopXX countries: {e}")

def parse_movie_translation(movie: dict) -> tuple:
    """Extract (title, content, slug) from movie translations dict."""
    trans_list = movie.get("trans", [])
    title = ""
    content = ""
    slug = ""
    for t in trans_list:
        if t.get("locale") == "vi":
            title = t.get("title") or title
            content = t.get("content") or t.get("seo_description") or content
            slug = t.get("slug") or slug
        elif t.get("locale") == "en" and not title:
            title = t.get("title") or title
            content = t.get("content") or t.get("seo_description") or content
            slug = t.get("slug") or slug
    if not title and trans_list:
        title = trans_list[0].get("title", "")
        content = trans_list[0].get("content", "")
    return title or "Untitled", content or "", slug or ""

def build_meta_preview(movie: dict) -> dict:
    """Build Stremio meta preview object for catalog."""
    code = movie.get("code")
    title, content, _ = parse_movie_translation(movie)
    thumbnail = movie.get("thumbnail") or ""
    quality = movie.get("quality", "")
    duration = movie.get("duration", "")
    
    genres = []
    for g in movie.get("genres", []):
        for t in g.get("trans", []):
            if t.get("locale") in ["vi", "en"]:
                genres.append(t.get("name"))
                break
                
    description = content
    if quality or duration:
        extra_info = []
        if quality: extra_info.append(f"Chất lượng: {quality}")
        if duration: extra_info.append(f"Thời lượng: {duration}")
        description = f"[{' | '.join(extra_info)}]\n\n" + description

    return {
        "id": f"topxx:{code}",
        "type": "movie",
        "name": title,
        "poster": thumbnail,
        "posterShape": "landscape" if "poster-" not in thumbnail else "poster",
        "description": description[:300] if description else "",
        "genres": genres
    }

async def fetch_catalog_items(base_endpoint: str, skip: int, limit: int = 30) -> List[dict]:
    """Dynamically fetch items from TopXX API handling varying per_page sizes (20 or 30)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    target_start = skip
    target_end = skip + limit
    delim = "&" if "?" in base_endpoint else "?"
    
    async with httpx.AsyncClient(headers=headers, timeout=10.0, follow_redirects=True) as client:
        try:
            # Fetch page 1 first to detect per_page size from metadata
            res1 = await client.get(f"{base_endpoint}{delim}page=1")
            if res1.status_code != 200:
                return []
            
            body1 = res1.json()
            meta = body1.get("meta", {})
            per_page = meta.get("per_page", 20) or 20
            total = meta.get("total", 0)
            
            if total > 0 and target_start >= total:
                return []
                
            start_page = (target_start // per_page) + 1
            end_page = ((target_end - 1) // per_page) + 1
            offset_in_concatenated = target_start % per_page
            
            accumulated_items = []
            for p in range(start_page, end_page + 1):
                if p == 1:
                    items = body1.get("data", [])
                else:
                    rp = await client.get(f"{base_endpoint}{delim}page={p}")
                    items = rp.json().get("data", []) if rp.status_code == 200 else []
                    
                accumulated_items.extend(items)
                if len(items) < per_page:
                    break
                    
            return accumulated_items[offset_in_concatenated : offset_in_concatenated + limit]
        except Exception as e:
            logger.error(f"Error fetching catalog items ({base_endpoint}): {e}")
            return []

def parse_stremio_extra(extra_path: Optional[str], query_params: dict):
    """Parse Stremio extra path (e.g. genre=Vi%E1%BB%87t%20Nam&skip=100.json) and query params."""
    genre = None
    search = None
    skip = 0
    
    # 1. Query parameters
    if "genre" in query_params: genre = query_params["genre"]
    if "search" in query_params: search = query_params["search"]
    if "skip" in query_params:
        try: skip = int(query_params["skip"])
        except (ValueError, TypeError): pass

    # 2. Path parameters
    if extra_path:
        clean_extra = extra_path
        if clean_extra.endswith(".json"):
            clean_extra = clean_extra[:-5]
            
        parts = re.split(r'[/&]', clean_extra)
        for part in parts:
            if not part:
                continue
            if "=" in part:
                k, v = part.split("=", 1)
                k = urllib.parse.unquote(k).strip()
                v = urllib.parse.unquote(v).strip()
                if k == "genre" and not genre:
                    genre = v
                elif k == "search" and not search:
                    search = v
                elif k == "skip":
                    try:
                        skip = int(v)
                    except (ValueError, TypeError):
                        pass

    return genre, search, max(0, skip)

# ------------------------------------------------------------------
# Catalog Endpoints
# ------------------------------------------------------------------
@topxx_router.get("/topxx/catalog/{type}/{id}.json")
@topxx_router.get("/catalog/{type}/{id}.json")
@topxx_router.get("/topxx/catalog/{type}/{id}/{extra:path}")
@topxx_router.get("/catalog/{type}/{id}/{extra:path}")
async def get_catalog(
    request: Request,
    type: str,
    id: str,
    extra: Optional[str] = None
):
    if type != "movie":
        return JSONResponse({"metas": []})

    if not GENRES_CACHE or not COUNTRIES_CACHE:
        await refresh_mappings()

    query_params = dict(request.query_params)
    genre, search, skip_val = parse_stremio_extra(extra, query_params)

    # Build target base endpoint
    base_endpoint = None
    if search:
        search_query = search.strip()
        base_endpoint = f"{TOPXX_API_BASE}/movies/search?q={urllib.parse.quote(search_query)}"
    elif genre:
        genre_clean = genre.strip()
        g_norm = normalize_key(genre_clean)
        
        if g_norm in GENRES_CACHE:
            g_code = GENRES_CACHE[g_norm]
            base_endpoint = f"{TOPXX_API_BASE}/genres/{g_code}/movies"
        elif g_norm in COUNTRIES_CACHE:
            c_code = COUNTRIES_CACHE[g_norm]
            base_endpoint = f"{TOPXX_API_BASE}/countries/{c_code}/movies"
        else:
            base_endpoint = f"{TOPXX_API_BASE}/movies/search?q={urllib.parse.quote(genre_clean)}"
    else:
        if id == "topxx_phim_hom_nay":
            base_endpoint = f"{TOPXX_API_BASE}/movies/today"
        else:
            base_endpoint = f"{TOPXX_API_BASE}/movies/latest"

    # Dynamically fetch items based on per_page meta
    sliced_items = await fetch_catalog_items(base_endpoint, skip=skip_val, limit=30)
    metas = [build_meta_preview(item) for item in sliced_items]

    return JSONResponse({"metas": metas})

# ------------------------------------------------------------------
# Meta Endpoint
# ------------------------------------------------------------------
@topxx_router.get("/topxx/meta/{type}/{id}.json")
@topxx_router.get("/meta/{type}/{id}.json")
async def get_meta(type: str, id: str):
    if not id.startswith("topxx:"):
        return JSONResponse({"meta": {}})
    
    code = id.replace("topxx:", "")
    url = f"{TOPXX_API_BASE}/movies/{code}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    async with httpx.AsyncClient(headers=headers, timeout=10.0, follow_redirects=True) as client:
        try:
            res = await client.get(url)
            if res.status_code != 200:
                return JSONResponse({"meta": {}})
            
            payload = res.json()
            movie = payload.get("data", {})
            if not movie:
                return JSONResponse({"meta": {}})
            
            title, content, _ = parse_movie_translation(movie)
            thumbnail = movie.get("thumbnail") or ""
            quality = movie.get("quality", "")
            duration = movie.get("duration", "")
            
            genres = []
            for g in movie.get("genres", []):
                for t in g.get("trans", []):
                    if t.get("locale") in ["vi", "en"]:
                        genres.append(t.get("name"))
                        break
                        
            countries = []
            for c in movie.get("countries", []):
                for t in c.get("trans", []):
                    if t.get("locale") in ["vi", "en"]:
                        countries.append(t.get("name"))
                        break

            cast = []
            for a in movie.get("actors", []):
                for t in a.get("trans", []):
                    if t.get("name"):
                        cast.append(t.get("name"))
                        break

            background = thumbnail
            images = movie.get("images", [])
            if images and len(images) > 0:
                background = images[0].get("path", thumbnail)

            meta = {
                "id": id,
                "type": "movie",
                "name": title,
                "poster": thumbnail,
                "background": background,
                "description": content,
                "genres": genres,
                "countries": countries,
                "cast": cast,
                "runtime": duration
            }
            return JSONResponse({"meta": meta})

        except Exception as e:
            logger.error(f"Error fetching meta for TopXX item {id}: {e}")
            return JSONResponse({"meta": {}})

# ------------------------------------------------------------------
# Stream Endpoint
# ------------------------------------------------------------------
@topxx_router.get("/topxx/stream/{type}/{id}.json")
@topxx_router.get("/stream/{type}/{id}.json")
async def get_stream(request: Request, type: str, id: str):
    if not id.startswith("topxx:"):
        return JSONResponse({"streams": []})
    
    code = id.replace("topxx:", "")
    url = f"{TOPXX_API_BASE}/movies/{code}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    base_host = request.url.netloc
    scheme = request.url.scheme or "http"
    proxy_base = f"{scheme}://{base_host}"

    streams = []
    async with httpx.AsyncClient(headers=headers, timeout=10.0, follow_redirects=True) as client:
        try:
            res = await client.get(url)
            if res.status_code == 200:
                payload = res.json()
                data = payload.get("data", {})
                
                # Fetch sources list
                sources_list = payload.get("sources", []) or data.get("sources", [])
                
                for idx, src in enumerate(sources_list):
                    embed_code = src.get("embed_code")
                    if not embed_code:
                        link = src.get("link", "")
                        match = re.search(r'/player/([a-zA-Z0-9]+)', link)
                        if match:
                            embed_code = match.group(1)
                    
                    if not embed_code:
                        continue

                    direct_hls = f"https://embed.streamxx.net/backup-hls/{embed_code}/main.m3u8"
                    proxy_hls = f"{proxy_base}/topxx/stream_proxy?url={urllib.parse.quote(direct_hls, safe='')}&referer={urllib.parse.quote('https://embed.streamxx.net/', safe='')}"
                    web_player = f"https://embed.streamxx.net/player/{embed_code}"

                    # Direct HLS Stream
                    streams.append({
                        "name": "TopXX Cinema",
                        "title": f"⚡ [Server {idx+1}] HLS Trực Tiếp (1080p Full HD)",
                        "url": direct_hls
                    })

                    # Proxy Stream
                    streams.append({
                        "name": "TopXX Cinema",
                        "title": f"▶ [Server {idx+1}] Proxy Stremio",
                        "url": proxy_hls
                    })

                    # Web Embed Player
                    streams.append({
                        "name": "TopXX Cinema",
                        "title": f"🌐 [Server {idx+1}] Web Player",
                        "externalUrl": web_player
                    })

        except Exception as e:
            logger.error(f"Error fetching streams for TopXX item {id}: {e}")

    return JSONResponse({"streams": streams})

# ------------------------------------------------------------------
# Stream Proxy
# ------------------------------------------------------------------
def rewrite_m3u8_playlist(m3u8_text: str, base_m3u8_url: str, referer: str, proxy_endpoint_url: str) -> str:
    """Rewrite segment URLs inside .m3u8 playlist to route through local proxy."""
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

@topxx_router.get("/topxx/stream_proxy")
@topxx_router.get("/stream_proxy")
async def topxx_stream_proxy(request: Request, url: str, referer: Optional[str] = None):
    """Proxy video streams and m3u8 playlists for Stremio Player."""
    if not url:
        raise HTTPException(status_code=400, detail="Missing stream URL")
    
    if " " in url:
        url = url.replace(" ", "+")
        
    ref = referer or "https://embed.streamxx.net/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": ref
    }

    base_host = request.url.netloc
    scheme = request.url.scheme or "http"
    proxy_endpoint_url = f"{scheme}://{base_host}/topxx/stream_proxy"

    client = httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True)
    try:
        req = client.build_request("GET", url)
        res = await client.send(req, stream=True)

        if res.status_code not in (200, 206):
            await res.aclose()
            await client.aclose()
            raise HTTPException(status_code=res.status_code, detail=f"Upstream returned {res.status_code}")

        content_type = res.headers.get("content-type", "").lower()
        is_m3u8 = ("mpegurl" in content_type or "m3u8" in content_type or url.split("?")[0].endswith(".m3u8"))

        if is_m3u8:
            body_bytes = await res.aread()
            await res.aclose()
            await client.aclose()
            
            try:
                m3u8_text = body_bytes.decode("utf-8")
            except UnicodeDecodeError:
                m3u8_text = body_bytes.decode("utf-8", errors="replace")
                
            rewritten_text = rewrite_m3u8_playlist(m3u8_text, url, ref, proxy_endpoint_url)
            return Response(
                content=rewritten_text.encode("utf-8"),
                media_type="application/vnd.apple.mpegurl",
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "no-cache"
                }
            )
        else:
            async def stream_generator():
                try:
                    async for chunk in res.aiter_bytes(chunk_size=65536):
                        yield chunk
                finally:
                    await res.aclose()
                    await client.aclose()

            response_headers = {
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": res.headers.get("cache-control", "public, max-age=3600")
            }
            if "content-length" in res.headers:
                response_headers["content-length"] = res.headers["content-length"]
            if "content-range" in res.headers:
                response_headers["content-range"] = res.headers["content-range"]
            if "accept-ranges" in res.headers:
                response_headers["accept-ranges"] = res.headers["accept-ranges"]

            return StreamingResponse(
                stream_generator(),
                status_code=res.status_code,
                media_type=content_type or "video/MP2T",
                headers=response_headers
            )

    except Exception as e:
        await client.aclose()
        logger.error(f"TopXX stream proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import os
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="TopXX Stremio Addon")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(topxx_router, prefix="/topxx")
    app.include_router(topxx_router)
    
    port = int(os.getenv("PORT", 7071))
    print(f"🚀 Starting TopXX Stremio Addon on http://127.0.0.1:{port}/topxx/manifest.json")
    uvicorn.run(app, host="0.0.0.0", port=port)
