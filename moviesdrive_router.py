import logging
import asyncio
import urllib.parse
import re
import html
import time
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse, Response
import httpx
from bs4 import BeautifulSoup

class SafeStreamingResponse(StreamingResponse):
    async def __call__(self, scope, receive, send) -> None:
        async def safe_send(message):
            try:
                await send(message)
            except RuntimeError as e:
                err_str = str(e)
                if "shorter than Content-Length" in err_str or "longer than Content-Length" in err_str:
                    return
                raise e
            except Exception:
                return
        try:
            await super().__call__(scope, receive, safe_send)
        except RuntimeError as e:
            err_str = str(e)
            if "shorter than Content-Length" in err_str or "longer than Content-Length" in err_str:
                return
            raise e
        except Exception:
            return

logger = logging.getLogger("moviesdrive_addon")

moviesdrive_router = APIRouter(prefix="", tags=["moviesdrive"])

# ------------------------------------------------------------------
# Constants & Configuration
# ------------------------------------------------------------------
MOVIESDRIVE_BASE_URL = "https://new2.moviesdrive.christmas"
MOVIESDRIVE_BACKUP_URLS = [
    "https://new2.moviesdrive.christmas",
    "https://new1.moviesdrive.christmas",
    "https://moviesdrives.mov"
]

CINEMETA_API = "https://v3-cinemeta.strem.io/meta"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': f'{MOVIESDRIVE_BASE_URL}/'
}

# Genre / Category mapping for MoviesDrive
CATEGORIES_MAP = {
    "Action": "action",
    "Adventure": "adventure",
    "Animation": "animation",
    "Anime": "anime",
    "Bollywood": "bollywood",
    "Comedy": "comedy",
    "Crime": "crime",
    "Documentary": "documentary",
    "Drama": "drama",
    "Dual Audio": "dual-audio",
    "DV HDR": "dv-hdr",
    "Family": "family",
    "Fantasy": "fantasy",
    "Hindi Dubbed": "hindi-dubbed",
    "Hollywood": "hollywood",
    "Horror": "horror",
    "IMAX": "imax",
    "K Drama": "k-drama",
    "Mystery": "mystery",
    "Netflix": "netflix",
    "Romance": "romance",
    "Sci-Fi": "sifi",
    "South": "south",
    "Thriller": "triller",
    "War": "war",
    "2160p 4K": "2160p-4k"
}

GENRE_OPTIONS = list(CATEGORIES_MAP.keys())

# In-memory Caches
CACHE: Dict[str, Any] = {}
CACHE_TTL = 300  # 5 minutes
STREAM_CACHE_TTL = 1800  # 30 minutes for resolved streams

def get_cached(key: str) -> Optional[Any]:
    now = time.time()
    if key in CACHE:
        data, ts, ttl = CACHE[key]
        if now - ts < ttl:
            return data
    return None

def set_cached(key: str, data: Any, ttl: int = CACHE_TTL):
    if len(CACHE) > 1000:
        CACHE.clear()
    CACHE[key] = (data, time.time(), ttl)

# ------------------------------------------------------------------
# Manifest
# ------------------------------------------------------------------
MANIFEST = {
    "id": "com.stremio.moviesdrive.addon",
    "version": "1.0.0",
    "name": "MoviesDrive - 4K Movies & Series",
    "description": "Watch Hollywood, Bollywood, Dual Audio 4K UHD, 1080p, 720p Movies & TV Series from MoviesDrive with fast streaming.",
    "resources": [
        "catalog",
        {
            "name": "meta",
            "types": ["movie", "series"],
            "idPrefixes": ["moviesdrive:", "tt"]
        },
        {
            "name": "stream",
            "types": ["movie", "series"],
            "idPrefixes": ["moviesdrive:", "tt"]
        },
        {
            "name": "subtitles",
            "types": ["movie", "series"],
            "idPrefixes": ["moviesdrive:", "tt"]
        }
    ],
    "types": ["movie", "series"],
    "catalogs": [
        {
            "type": "movie",
            "id": "moviesdrive_movies_latest",
            "name": "MoviesDrive - Phim Mới",
            "extra": [
                {"name": "genre", "options": GENRE_OPTIONS, "isRequired": False},
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        },
        {
            "type": "movie",
            "id": "moviesdrive_movies_4k",
            "name": "MoviesDrive - Phim 4K UHD",
            "extra": [
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        },
        {
            "type": "series",
            "id": "moviesdrive_series_latest",
            "name": "MoviesDrive - Phim Bộ (Series)",
            "extra": [
                {"name": "genre", "options": GENRE_OPTIONS, "isRequired": False},
                {"name": "search", "isRequired": False},
                {"name": "skip", "isRequired": False}
            ]
        }
    ]
}

@moviesdrive_router.get("/moviesdrive/manifest.json")
@moviesdrive_router.get("/manifest.json")
async def get_manifest():
    return JSONResponse(MANIFEST)

# ------------------------------------------------------------------
# Core Scraper Logic
# ------------------------------------------------------------------
async def fetch_html(url: str, referer: Optional[str] = None) -> str:
    headers = dict(HEADERS)
    if referer:
        headers['Referer'] = referer
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        res = await client.get(url, headers=headers)
        if res.status_code == 200:
            return res.text
    return ""

async def search_moviesdrive_api(query: str, page: int = 1) -> Dict[str, Any]:
    cache_key = f"search:{query}:{page}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    url = f"{MOVIESDRIVE_BASE_URL}/search.php?q={urllib.parse.quote(query)}&page={page}"
    headers = {
        'User-Agent': HEADERS['User-Agent'],
        'Referer': f'{MOVIESDRIVE_BASE_URL}/search.html'
    }
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                set_cached(cache_key, data, ttl=300)
                return data
    except Exception as e:
        logger.warning(f"Error searching MoviesDrive API for '{query}': {e}")
    
    return {"hits": [], "found": 0}

def parse_quality_badge(title: str) -> str:
    t = title.lower()
    if '2160p' in t or '4k' in t:
        return '4K UHD'
    if '1080p' in t:
        return '1080p FHD'
    if '720p' in t:
        return '720p HD'
    if '480p' in t:
        return '480p'
    return 'HD'

async def get_catalog_items(cat_type: str, cat_id: str, genre: Optional[str] = None, search: Optional[str] = None, skip: int = 0) -> List[Dict[str, Any]]:
    page = (skip // 18) + 1
    items = []
    
    if search:
        data = await search_moviesdrive_api(search, page=page)
        hits = data.get('hits', [])
        for hit in hits:
            doc = hit.get('document', {})
            permalink = doc.get('permalink', '')
            slug = permalink.strip('/')
            title = doc.get('post_title', 'Untitled')
            thumb = doc.get('post_thumbnail', '')
            if not thumb.startswith('http') and thumb:
                thumb = urllib.parse.urljoin(MOVIESDRIVE_BASE_URL, thumb)
            
            is_series = bool(re.search(r'season|s\d+|series|episodes?|ep\d+', title, re.I))
            item_type = "series" if is_series else "movie"
            if cat_type and item_type != cat_type and not search:
                continue

            items.append({
                "id": f"moviesdrive:{slug}",
                "type": item_type,
                "name": title,
                "poster": thumb,
                "posterShape": "poster"
            })
        return items

    # Catalog by category or 4K or latest
    url = f"{MOVIESDRIVE_BASE_URL}/"
    if cat_id == "moviesdrive_movies_4k":
        url = f"{MOVIESDRIVE_BASE_URL}/category/2160p-4k/"
    elif genre and genre in CATEGORIES_MAP:
        url = f"{MOVIESDRIVE_BASE_URL}/category/{CATEGORIES_MAP[genre]}/"
    elif cat_type == "series":
        url = f"{MOVIESDRIVE_BASE_URL}/category/web/"
    
    if page > 1:
        url = f"{url}page/{page}/"

    cache_key = f"cat:{url}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    page_html = await fetch_html(url)
    if not page_html:
        return []

    soup = BeautifulSoup(page_html, 'html.parser')
    
    cards = soup.find_all('div', class_='poster-card')
    if cards:
        for card in cards:
            a_tag = card.find_parent('a', href=True) or card.find('a', href=True)
            if not a_tag:
                continue
            href = a_tag['href']
            slug = href.replace(MOVIESDRIVE_BASE_URL, '').strip('/')
            if not slug or any(k in slug.lower() for k in ['category', 'tag', 'contact', 'dmca', 'privacy']):
                continue

            img_tag = card.find('img')
            title_el = card.find(['p', 'h2', 'h3', 'h4', 'span'], class_=lambda c: c and 'title' in c) or card.find(['p', 'h2', 'h3'])
            title = (title_el.get_text(strip=True) if title_el else a_tag.get('title') or img_tag.get('alt') if img_tag else '') or slug.replace('-', ' ').title()
            
            thumb = img_tag.get('src') or img_tag.get('data-src') or '' if img_tag else ''
            if not thumb.startswith('http') and thumb:
                thumb = urllib.parse.urljoin(MOVIESDRIVE_BASE_URL, thumb)

            is_series = bool(re.search(r'season|s\d+|series|episodes?|ep\d+', title, re.I))
            item_type = "series" if is_series else "movie"

            items.append({
                "id": f"moviesdrive:{slug}",
                "type": item_type,
                "name": title,
                "poster": thumb,
                "posterShape": "poster"
            })
    else:
        articles = soup.find_all('article')
        for art in articles:
            a_tag = art.find('a', href=True)
            img_tag = art.find('img')
            title_tag = art.find(['h2', 'h3', 'h4'])
            
            if not a_tag:
                continue
            href = a_tag['href']
            slug = href.replace(MOVIESDRIVE_BASE_URL, '').strip('/')
            if not slug or any(k in slug.lower() for k in ['category', 'tag', 'contact', 'dmca', 'privacy']):
                continue
            
            title = (title_tag.get_text(strip=True) if title_tag else a_tag.get_text(strip=True)) or "Untitled"
            thumb = img_tag.get('src') or img_tag.get('data-src') or '' if img_tag else ''
            if not thumb.startswith('http') and thumb:
                thumb = urllib.parse.urljoin(MOVIESDRIVE_BASE_URL, thumb)

            is_series = bool(re.search(r'season|s\d+|series|episodes?|ep\d+', title, re.I))
            item_type = "series" if is_series else "movie"

            items.append({
                "id": f"moviesdrive:{slug}",
                "type": item_type,
                "name": title,
                "poster": thumb,
                "posterShape": "poster"
            })

    set_cached(cache_key, items, ttl=300)
    return items

# ------------------------------------------------------------------
# Catalog Endpoints
# ------------------------------------------------------------------
@moviesdrive_router.get("/moviesdrive/catalog/{type}/{id}.json")
@moviesdrive_router.get("/catalog/{type}/{id}.json")
async def catalog_endpoint(type: str, id: str, genre: Optional[str] = None, search: Optional[str] = None, skip: Optional[int] = 0):
    metas = await get_catalog_items(type, id, genre=genre, search=search, skip=skip or 0)
    return JSONResponse({"metas": metas})

@moviesdrive_router.get("/moviesdrive/catalog/{type}/{id}/{extra}.json")
@moviesdrive_router.get("/catalog/{type}/{id}/{extra}.json")
async def catalog_extra_endpoint(type: str, id: str, extra: str):
    genre = None
    search = None
    skip = 0
    if extra:
        pairs = extra.split("&")
        for pair in pairs:
            if "=" in pair:
                k, v = pair.split("=", 1)
                v = urllib.parse.unquote(v)
                if k == "genre":
                    genre = v
                elif k == "search":
                    search = v
                elif k == "skip":
                    try:
                        skip = int(v)
                    except ValueError:
                        pass
    metas = await get_catalog_items(type, id, genre=genre, search=search, skip=skip)
    return JSONResponse({"metas": metas})

# ------------------------------------------------------------------
# Meta Endpoints
# ------------------------------------------------------------------
@moviesdrive_router.get("/moviesdrive/meta/{type}/{id}.json")
@moviesdrive_router.get("/meta/{type}/{id}.json")
async def meta_endpoint(type: str, id: str):
    if not id.startswith("moviesdrive:"):
        return JSONResponse({"meta": {}})
    
    slug = id.replace("moviesdrive:", "").strip("/")
    post_url = f"{MOVIESDRIVE_BASE_URL}/{slug}/"
    
    cache_key = f"meta:{slug}"
    cached = get_cached(cache_key)
    if cached is not None:
        return JSONResponse({"meta": cached})

    page_html = await fetch_html(post_url)
    if not page_html:
        return JSONResponse({"meta": {}})

    soup = BeautifulSoup(page_html, 'html.parser')
    title_tag = soup.find('h1') or soup.find('h2')
    name = title_tag.get_text(strip=True) if title_tag else slug.replace("-", " ").title()
    
    content = soup.find('div', class_='entry-content') or soup.find('article') or soup
    img_tag = content.find('img') if content else None
    poster = img_tag.get('src') if img_tag else ""
    if not poster.startswith('http') and poster:
        poster = urllib.parse.urljoin(MOVIESDRIVE_BASE_URL, poster)

    # Extract plot/synopsis
    description = ""
    paragraphs = content.find_all('p') if content else []
    for p in paragraphs:
        txt = p.get_text(strip=True)
        if len(txt) > 80 and not any(k in txt.lower() for k in ['download', 'link', 'click here', 'telegram', 'join']):
            description = txt
            break

    # Check for series episodes
    is_series = bool(type == "series" or re.search(r'season|s\d+|series', name, re.I))
    videos = []
    
    if is_series:
        season_match = re.search(r'season\s*(\d+)|s(\d+)', name, re.I)
        season_num = int(season_match.group(1) or season_match.group(2)) if season_match else 1
        
        ep_count = 12
        # Check archive pages on mdrive.lol to get exact episode count
        archive_a = [a['href'] for a in content.find_all('a', href=True) if 'archive/' in a['href'] or 'mdrive.' in a['href']]
        if archive_a:
            try:
                arc_html = await fetch_html(archive_a[0], referer=post_url)
                arc_soup = BeautifulSoup(arc_html, 'html.parser')
                hc_links = [a['href'] for a in arc_soup.find_all('a', href=True) if 'hubcloud' in a['href'] or 'gdflix' in a['href']]
                if hc_links:
                    ep_count = len(hc_links)
            except Exception:
                pass
        else:
            ep_match = re.findall(r'ep\s*(\d+)|episode\s*(\d+)', page_html, re.I)
            if ep_match:
                try:
                    numbers = [int(m[0] or m[1]) for m in ep_match if (m[0] or m[1])]
                    if numbers:
                        ep_count = min(max(numbers), 60)
                except Exception:
                    pass

        for ep in range(1, ep_count + 1):
            videos.append({
                "id": f"moviesdrive:{slug}:{season_num}:{ep}",
                "title": f"Tập {ep} (Episode {ep})",
                "season": season_num,
                "episode": ep,
                "released": "2026-01-01T00:00:00.000Z"
            })

    meta_obj = {
        "id": id,
        "type": "series" if is_series else "movie",
        "name": name,
        "poster": poster,
        "background": poster,
        "description": description or f"Watch {name} on MoviesDrive in 4K UHD, 1080p, 720p.",
        "genres": ["Action", "HD", "Dual Audio"],
        "posterShape": "poster"
    }
    if videos:
        meta_obj["videos"] = videos

    set_cached(cache_key, meta_obj, ttl=600)
    return JSONResponse({"meta": meta_obj})

# ------------------------------------------------------------------
# Stream Resolver Helpers (HubCloud, Archives & Gateway Resolution)
# ------------------------------------------------------------------
async def resolve_all_download_buttons_from_post(post_url: str) -> List[Dict[str, Any]]:
    """Extract all HubCloud and Mdrive archive download buttons from post page with season tracking."""
    html_content = await fetch_html(post_url)
    if not html_content:
        return []
    soup = BeautifulSoup(html_content, 'html.parser')
    content = soup.find('div', class_='entry-content') or soup.find('article') or soup
    results = []
    
    current_season = None
    for elem in content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'div']):
        text = elem.get_text(" ", strip=True)
        s_match = re.search(r'\bseason\s*(\d+)\b', text, re.I)
        if s_match:
            current_season = int(s_match.group(1))
            
        for a in elem.find_all('a', href=True):
            href = a['href']
            btn_text = a.get_text(strip=True)
            if any(k in href for k in ['hubcloud', 'archive/', 'mdrive.', 'kolop', 'katdrive', 'fastdl']):
                if not any(k in href.lower() for k in ['category', 'tag', 'telegram', 'join']):
                    btn_season = current_season
                    bs_match = re.search(r'\bs(\d+)\b|\bseason\s*(\d+)\b', btn_text, re.I)
                    if bs_match:
                        btn_season = int(bs_match.group(1) or bs_match.group(2))
                    results.append({'text': btn_text, 'url': href, 'season': btn_season})
    return results

async def resolve_archive_page_episodes(archive_url: str, post_url: str, episode_num: int = 1) -> Optional[str]:
    """From an mdrive.lol/archive/<id>/ page, extract the hubcloud link corresponding to episode_num."""
    cache_key = f"arc:{archive_url}:{episode_num}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(archive_url, headers={'User-Agent': HEADERS['User-Agent'], 'Referer': post_url})
            soup = BeautifulSoup(resp.text, 'html.parser')
            hc_links = []
            for a in soup.find_all('a', href=True):
                if 'hubcloud' in a['href']:
                    hc_links.append(a['href'])
            if len(hc_links) >= episode_num:
                res = hc_links[episode_num - 1]
                set_cached(cache_key, res, ttl=1800)
                return res
    except Exception as e:
        logger.warning(f"Error fetching archive page {archive_url}: {e}")
    return None

async def resolve_hubcloud_files_from_url(hubcloud_url: str, filter_query: Optional[str] = None) -> List[Dict[str, Any]]:
    """Query HubCloud search API to get individual .mkv files."""
    cache_key = f"hc_files:{hubcloud_url}:{filter_query}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(hubcloud_url, headers={'User-Agent': HEADERS['User-Agent'], 'Referer': f'{MOVIESDRIVE_BASE_URL}/'})
            page_html = resp.text
            final_url = str(resp.url)
            
            token_match = re.search(r'const FROM_AC_TOKEN\s*=\s*"([^"]+)"', page_html)
            if not token_match:
                return []
            token_val = token_match.group(1)
            
            q_match = re.search(r'const Q_INITIAL\s*=\s*"([^"]+)"', page_html)
            q_val = q_match.group(1) if q_match else ""
            try:
                q_val = q_val.encode('utf-8').decode('unicode-escape')
            except Exception:
                pass
            q_val = html.unescape(q_val)
            clean_q = re.sub(r'[\r\n\t]', ' ', q_val).strip()
            
            search_query = filter_query if filter_query else clean_q

            api_url = f"https://hubcloud.cx/drive/search-recover.php?api=search&q={urllib.parse.quote(search_query)}&page=1&from_ac={token_val}"
            api_resp = await client.get(api_url, headers={'User-Agent': HEADERS['User-Agent'], 'Referer': final_url, 'Accept': 'application/json'})
            if api_resp.status_code == 200:
                data = api_resp.json()
                hits = data.get('hits', [])
                set_cached(cache_key, hits, ttl=600)
                return hits
    except Exception as e:
        logger.warning(f"Error querying HubCloud search API: {e}")
    return []

async def resolve_direct_stream_links(hubcloud_file_url: str) -> List[Dict[str, str]]:
    """Extract direct fast streaming links (Workers/Google CDN/Pixel) from a file URL."""
    cache_key = f"stream:{hubcloud_file_url}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    streams = []
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            # Step 1: fetch file drive page on HubCloud
            resp1 = await client.get(hubcloud_file_url, headers={'User-Agent': HEADERS['User-Agent'], 'Referer': 'https://hubcloud.cx/'})
            soup1 = BeautifulSoup(resp1.text, 'html.parser')
            gamer_link = None
            for a in soup1.find_all('a', href=True):
                if 'gamerxyt.com' in a['href']:
                    gamer_link = a['href']
                    break
            if not gamer_link:
                return []
                
            # Step 2: fetch gamerxyt page
            resp2 = await client.get(gamer_link, headers={'User-Agent': HEADERS['User-Agent'], 'Referer': hubcloud_file_url})
            soup2 = BeautifulSoup(resp2.text, 'html.parser')
            
            for a in soup2.find_all('a', href=True):
                href = a['href']
                text = a.get_text(strip=True)
                
                # 1. Cloudflare R2 direct high-speed video stream
                if 'r2.cloudflarestorage.com' in href or 'cloudflarestorage.com' in href:
                    if not any(k in href.lower() for k in ['.zip', '.rar']) and not any(k in text.lower() for k in ['zip', 'pack']):
                        streams.append({'type': '⚡ FSL Server (Cloudflare R2 10Gbps)', 'url': href})
                
                # 2. Cloudflare Workers high-speed video stream
                elif 'workers.dev' in href:
                    p = urllib.parse.urlsplit(href)
                    clean_path = urllib.parse.quote(p.path)
                    clean_url = urllib.parse.urlunsplit((p.scheme, p.netloc, clean_path, p.query, p.fragment))
                    streams.append({'type': '⚡ Worker CDN 10Gbps', 'url': clean_url})

            if streams:
                set_cached(cache_key, streams, ttl=STREAM_CACHE_TTL)
    except Exception as e:
        logger.warning(f"Error resolving direct streams for {hubcloud_file_url}: {e}")

    return streams

async def get_cinemeta_title(item_type: str, imdb_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve title and release year for IMDb id from Cinemeta."""
    cache_key = f"cinemeta:{imdb_id}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    url = f"{CINEMETA_API}/{item_type}/{imdb_id}.json"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json().get('meta', {})
                set_cached(cache_key, data, ttl=3600)
                return data
    except Exception as e:
        logger.warning(f"Cinemeta error for {imdb_id}: {e}")
    return None

async def fetch_opensubtitles(imdb_id: str, media_type: str = "movie") -> list:
    """Fetch matching OpenSubtitles tracks (Vietnamese, English) for Stremio players."""
    if not imdb_id or not imdb_id.startswith("tt"):
        return []
    url = f"https://opensubtitles-v3.strem.io/subtitles/{media_type}/{urllib.parse.quote(imdb_id)}.json"
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                subs = resp.json().get("subtitles", [])
                return [s for s in subs if s.get("lang") in ("vie", "vi", "eng")]
    except Exception as e:
        logger.warning(f"OpenSubtitles fetch failed for {imdb_id}: {e}")
    return []

# ------------------------------------------------------------------
# Stream Endpoints
# ------------------------------------------------------------------
@moviesdrive_router.get("/moviesdrive/stream/{type}/{id}.json")
@moviesdrive_router.get("/stream/{type}/{id}.json")
async def stream_endpoint(request: Request, type: str, id: str):
    streams = []
    base_proxy = str(request.base_url).rstrip('/') + "/moviesdrive/stream_proxy"

    # Case 1: Custom MoviesDrive ID (e.g. moviesdrive:spooky-in-love-season-1-2026:1:1)
    if id.startswith("moviesdrive:"):
        parts = id.split(":")
        slug = parts[1]
        season_num = int(parts[2]) if len(parts) > 2 else None
        episode_num = int(parts[3]) if len(parts) > 3 else (1 if type == "series" else None)
        
        post_url = f"{MOVIESDRIVE_BASE_URL}/{slug}/"
        buttons = await resolve_all_download_buttons_from_post(post_url)
        
        # Check if buttons are archive links (mdrive.lol/archive/<id>/) or search-recover
        archive_buttons = [
            b for b in buttons 
            if ('archive/' in b['url'] or 'mdrive.' in b['url']) 
            and not any(k in b['text'].lower() for k in ['zip', 'pack', 'complete', 'season zip', 'rar'])
        ]
        direct_hc_buttons = [b for b in buttons if 'hubcloud' in b['url']]

        # If archive buttons exist (used for both movies and series)
        if archive_buttons:
            if season_num is not None:
                season_matched = [b for b in archive_buttons if b.get('season') == season_num]
                if season_matched:
                    archive_buttons = season_matched
            target_ep = episode_num if (type == "series" and episode_num is not None) else 1
            tasks = [resolve_archive_page_episodes(b['url'], post_url, episode_num=target_ep) for b in archive_buttons]
            ep_hc_links = await asyncio.gather(*tasks, return_exceptions=True)
            
            valid_hc_links = []
            for b, hc in zip(archive_buttons, ep_hc_links):
                if isinstance(hc, str) and hc:
                    valid_hc_links.append({'quality': b['text'], 'url': hc})

            # Resolve direct streams
            stream_tasks = [resolve_direct_stream_links(item['url']) for item in valid_hc_links]
            stream_results = await asyncio.gather(*stream_tasks, return_exceptions=True)

            for item, s_res in zip(valid_hc_links, stream_results):
                if isinstance(s_res, list) and s_res:
                    quality = parse_quality_badge(item['quality'])
                    for s in s_res:
                        direct_url = s['url']
                        proxied_url = f"{base_proxy}?url={urllib.parse.quote(direct_url, safe='')}"
                        
                        clean_fn = f"{slug}.mkv" if type == "movie" else f"{slug}.S0{season_num or 1}E0{target_ep}.mkv"
                        stream_title = f"{slug} - Ep {target_ep} [{item['quality']}]\n{s['type']}" if type == "series" else f"{slug} [{item['quality']}]\n{s['type']}"
                        
                        streams.append({
                            "name": f"🎬 MoviesDrive [{quality}]",
                            "title": stream_title,
                            "url": proxied_url,
                            "behaviorHints": {
                                "notWebReady": False,
                                "filename": clean_fn
                            }
                        })

        if streams:
            try:
                from subtitles_service import STREAM_VIDEO_URL_CACHE, get_or_generate_synced_vtt
                first_direct_url = None
                for s_res in stream_results:
                    if isinstance(s_res, list) and s_res:
                        for s in s_res:
                            if s.get("url") and s["url"].startswith("http"):
                                first_direct_url = s["url"]
                                break
                        if first_direct_url:
                            break
                if first_direct_url:
                    STREAM_VIDEO_URL_CACHE[id] = first_direct_url
                    asyncio.create_task(get_or_generate_synced_vtt(type, id, video_url=first_direct_url))
            except Exception as e:
                logger.warning(f"Pre-translation trigger error: {e}")

        # If search-recover HubCloud buttons exist
        if not streams and direct_hc_buttons:
            filter_q = None
            if season_num is not None and episode_num is not None:
                filter_q = f"S{season_num:02d}E{episode_num:02d}"

            tasks = [resolve_hubcloud_files_from_url(b['url'], filter_query=filter_q) for b in direct_hc_buttons[:6]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            all_files = []
            for r in results:
                if isinstance(r, list):
                    all_files.extend(r)

            unique_files = {}
            for f in all_files:
                if f.get('url') and f['url'] not in unique_files:
                    fn = f.get('file_name', '')
                    if season_num is not None and episode_num is not None:
                        ep_pat = rf'S0?{season_num}.*?E0?{episode_num}\b|EP0?{episode_num}\b'
                        if not re.search(ep_pat, fn, re.I):
                            continue
                    unique_files[f['url']] = f

            stream_tasks = [resolve_direct_stream_links(f_url) for f_url in list(unique_files.keys())[:5]]
            stream_results = await asyncio.gather(*stream_tasks, return_exceptions=True)

            for f_url, s_res in zip(list(unique_files.keys())[:5], stream_results):
                if isinstance(s_res, list) and s_res:
                    f_info = unique_files[f_url]
                    file_name = f_info.get('file_name', 'Movie')
                    file_size = f_info.get('size', '')
                    quality = parse_quality_badge(file_name)
                    
                    for s in s_res:
                        direct_url = s['url']
                        proxied_url = f"{base_proxy}?url={urllib.parse.quote(direct_url, safe='')}&referer={urllib.parse.quote('https://gamerxyt.com/', safe='')}"
                        
                        streams.append({
                            "name": f"🎬 MoviesDrive [{quality}]",
                            "title": f"{file_name}\n💾 Size: {file_size} | {s['type']}",
                            "url": proxied_url,
                            "behaviorHints": {
                                "notWebReady": False
                            }
                        })

    # Case 2: IMDb ID (e.g. tt6263850 or tt0903747:1:1)
    elif id.startswith("tt"):
        parts = id.split(":")
        imdb_id = parts[0]
        season_num = int(parts[1]) if len(parts) > 1 else None
        episode_num = int(parts[2]) if len(parts) > 2 else (1 if type == "series" else None)
        
        meta = await get_cinemeta_title(type, imdb_id)
        if meta and meta.get('name'):
            title = meta['name']
            year = meta.get('year', '')
            
            search_query = f"{title}"
            search_data = await search_moviesdrive_api(search_query, page=1)
            hits = search_data.get('hits', [])
            
            if not hits and year:
                search_data = await search_moviesdrive_api(f"{title} {year}", page=1)
                hits = search_data.get('hits', [])

            if hits:
                first_post = hits[0].get('document', {}).get('permalink', '')
                if first_post:
                    post_url = urllib.parse.urljoin(MOVIESDRIVE_BASE_URL, first_post)
                    buttons = await resolve_all_download_buttons_from_post(post_url)
                    
                    archive_buttons = [
                        b for b in buttons 
                        if ('archive/' in b['url'] or 'mdrive.' in b['url']) 
                        and not any(k in b['text'].lower() for k in ['zip', 'pack', 'complete', 'season zip', 'rar'])
                    ]
                    direct_hc_buttons = [b for b in buttons if 'hubcloud' in b['url']]

                    if archive_buttons:
                        if season_num is not None:
                            season_matched = [b for b in archive_buttons if b.get('season') == season_num]
                            if season_matched:
                                archive_buttons = season_matched
                        target_ep = episode_num if (type == "series" and episode_num is not None) else 1
                        tasks = [resolve_archive_page_episodes(b['url'], post_url, episode_num=target_ep) for b in archive_buttons]
                        ep_hc_links = await asyncio.gather(*tasks, return_exceptions=True)
                        
                        valid_hc_links = []
                        for b, hc in zip(archive_buttons, ep_hc_links):
                            if isinstance(hc, str) and hc:
                                valid_hc_links.append({'quality': b['text'], 'url': hc})

                        stream_tasks = [resolve_direct_stream_links(item['url']) for item in valid_hc_links]
                        stream_results = await asyncio.gather(*stream_tasks, return_exceptions=True)

                        subs = await fetch_opensubtitles(id, type)
                        for item, s_res in zip(valid_hc_links, stream_results):
                            if isinstance(s_res, list) and s_res:
                                quality = parse_quality_badge(item['quality'])
                                for s in s_res:
                                    direct_url = s['url']
                                    proxied_url = f"{base_proxy}?url={urllib.parse.quote(direct_url, safe='')}"
                                    
                                    clean_fn = f"{title}.mkv" if type == "movie" else f"{title}.S0{season_num or 1}E0{target_ep}.mkv"
                                    stream_title = f"{title} - Ep {target_ep} [{item['quality']}]\n{s['type']}" if type == "series" else f"{title} [{item['quality']}]\n{s['type']}"
                                    
                                    # Primary Direct Stream
                                    streams.append({
                                        "name": f"🎬 MoviesDrive [{quality}]",
                                        "title": f"{stream_title} (Direct)",
                                        "url": direct_url,
                                        "behaviorHints": {
                                            "notWebReady": False,
                                            "filename": clean_fn
                                        }
                                    })
                                    # Proxy Stream (for players behind strict proxies)
                                    streams.append({
                                        "name": f"🎬 MoviesDrive Proxy [{quality}]",
                                        "title": f"{stream_title} (Proxy)",
                                        "url": proxied_url,
                                        "behaviorHints": {
                                            "notWebReady": False,
                                            "filename": clean_fn
                                        }
                                    })

                    if not streams and direct_hc_buttons:
                        filter_q = None
                        if season_num is not None and episode_num is not None:
                            filter_q = f"S{season_num:02d}E{episode_num:02d}"

                        tasks = [resolve_hubcloud_files_from_url(b['url'], filter_query=filter_q) for b in direct_hc_buttons[:5]]
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        
                        all_files = []
                        for r in results:
                            if isinstance(r, list):
                                all_files.extend(r)

                        unique_files = {}
                        for f in all_files:
                            if f.get('url') and f['url'] not in unique_files:
                                fn = f.get('file_name', '')
                                if season_num is not None and episode_num is not None:
                                    ep_pat = rf'S0?{season_num}.*?E0?{episode_num}\b|EP0?{episode_num}\b'
                                    if not re.search(ep_pat, fn, re.I):
                                        continue
                                unique_files[f['url']] = f

                        stream_tasks = [resolve_direct_stream_links(f_url) for f_url in list(unique_files.keys())[:5]]
                        stream_results = await asyncio.gather(*stream_tasks, return_exceptions=True)

                        for f_url, s_res in zip(list(unique_files.keys())[:5], stream_results):
                            if isinstance(s_res, list) and s_res:
                                f_info = unique_files[f_url]
                                file_name = f_info.get('file_name', title)
                                file_size = f_info.get('size', '')
                                quality = parse_quality_badge(file_name)
                                
                                for s in s_res:
                                    direct_url = s['url']
                                    proxied_url = f"{base_proxy}?url={urllib.parse.quote(direct_url, safe='')}&referer={urllib.parse.quote('https://gamerxyt.com/', safe='')}"
                                    
                                    # Primary Direct Stream
                                    streams.append({
                                        "name": f"🎬 MoviesDrive [{quality}]",
                                        "title": f"{file_name}\n💾 {file_size} | {s['type']} (Direct)",
                                        "url": direct_url,
                                        "behaviorHints": {
                                            "notWebReady": False
                                        }
                                    })
                                    # Proxy Stream
                                    streams.append({
                                        "name": f"🎬 MoviesDrive Proxy [{quality}]",
                                        "title": f"{file_name}\n💾 {file_size} | 🛡️ Local Proxy Stream",
                                        "url": proxied_url,
                                        "behaviorHints": {
                                            "notWebReady": False
                                        }
                                    })

    if streams:
        try:
            from subtitles_service import STREAM_VIDEO_URL_CACHE, get_or_generate_synced_vtt
            first_direct = streams[0].get("url")
            if first_direct:
                STREAM_VIDEO_URL_CACHE[id] = first_direct
                asyncio.create_task(get_or_generate_synced_vtt(type, id, video_url=first_direct))
        except Exception:
            pass

    return JSONResponse({"streams": streams})

# ------------------------------------------------------------------
# High-Speed Range Streaming Proxy
# ------------------------------------------------------------------
@moviesdrive_router.get("/moviesdrive/stream_proxy")
@moviesdrive_router.get("/stream_proxy")
async def moviesdrive_stream_proxy(request: Request, url: str, referer: Optional[str] = None):
    """Proxy direct video stream with full HTTP Range request forwarding for instant seek/scrubbing."""
    if not url:
        raise HTTPException(status_code=400, detail="Missing stream URL")
    clean_url = urllib.parse.unquote(url)
    
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }
    
    # Do not send Referer for Cloudflare R2 / S3 signed URLs or Google CDN URLs as AWS signatures strictly enforce host header only
    if referer and not any(k in clean_url for k in ["cloudflarestorage.com", "r2.cloudflarestorage.com", "googleusercontent.com"]):
        req_headers["Referer"] = referer
    
    range_header = request.headers.get("range")
    if range_header:
        req_headers["range"] = range_header

    try:
        client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)
        upstream_req = client.build_request("GET", clean_url, headers=req_headers)
        upstream_resp = await client.send(upstream_req, stream=True)

        resp_headers = {}
        for k in ["content-range", "content-type", "accept-ranges"]:
            if k in upstream_resp.headers:
                resp_headers[k] = upstream_resp.headers[k]
                
        if "content-type" not in resp_headers:
            resp_headers["content-type"] = "video/x-matroska"
            
        resp_headers["accept-ranges"] = "bytes"
        resp_headers["Access-Control-Allow-Origin"] = "*"

        async def stream_generator():
            try:
                async for chunk in upstream_resp.aiter_bytes(chunk_size=128 * 1024):
                    yield chunk
            except Exception:
                pass
            finally:
                try:
                    await upstream_resp.aclose()
                except Exception:
                    pass
                try:
                    await client.aclose()
                except Exception:
                    pass

        return SafeStreamingResponse(
            stream_generator(),
            status_code=upstream_resp.status_code,
            headers=resp_headers
        )
    except Exception as e:
        logger.error(f"Stream proxy exception for {url}: {e}")
        raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}")

# ------------------------------------------------------------------
# Subtitles Endpoint (Bridges OpenSubtitles & Stremio for MoviesDrive items)
# ------------------------------------------------------------------
async def find_imdb_for_moviesdrive_id(media_type: str, md_id: str) -> Optional[str]:
    """Resolve MoviesDrive slug ID to IMDb ID via Cinemeta search."""
    cache_key = f"md_to_imdb:{md_id}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    parts = md_id.split(":")
    slug = parts[1]
    season = int(parts[2]) if len(parts) > 2 else 1
    episode = int(parts[3]) if len(parts) > 3 else 1

    clean = slug
    for w in ['web-dl', 'hindi', 'dd5-1', 'english', '480p', '720p', '1080p', '2160p', '4k', 'sdr', 'x264', 'esubs', 'full-movie', 'esub']:
        clean = re.sub(rf'\b{w}\b', '', clean, flags=re.I)

    clean_title = re.sub(r'\b(19\d\d|20\d\d)\b', '', clean)
    clean_title = re.sub(r'season-\d+', '', clean_title, flags=re.I)
    clean_title = clean_title.replace('-', ' ').strip()

    cinemeta_url = f"https://v3-cinemeta.strem.io/catalog/{media_type}/top/search={urllib.parse.quote(clean_title)}.json"
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(cinemeta_url)
            if resp.status_code == 200:
                metas = resp.json().get("metas", [])
                if metas:
                    imdb_id = metas[0].get('imdb_id') or metas[0].get('id')
                    if imdb_id:
                        final_id = f"{imdb_id}:{season}:{episode}" if media_type == "series" else imdb_id
                        set_cached(cache_key, final_id, ttl=86400)
                        return final_id
    except Exception as e:
        logger.warning(f"Error resolving IMDb ID for {md_id}: {e}")
    return None

@moviesdrive_router.api_route("/moviesdrive/subtitles/vtt/{item_id}.vtt", methods=["GET", "HEAD"])
@moviesdrive_router.api_route("/subtitles/vtt/{item_id}.vtt", methods=["GET", "HEAD"])
async def serve_synced_vtt(request: Request, item_id: str, type: str = "movie"):
    """Serves exact synced Vietnamese VTT subtitle track with HEAD request support and full track fallback."""
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Content-Disposition": "inline",
        "Cache-Control": "public, max-age=86400"
    }
    if request.method == "HEAD":
        return Response(status_code=200, media_type="text/vtt; charset=utf-8", headers=headers)

    target_id = request.query_params.get("orig_id") or item_id
    from subtitles_service import get_or_generate_synced_vtt
    try:
        vtt_content = await get_or_generate_synced_vtt(type, target_id)
    except Exception as e:
        logger.warning(f"Error in serve_synced_vtt for {target_id}: {e}")
        vtt_content = None

    if not vtt_content or not vtt_content.strip():
        vtt_content = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:05.000\n[Đang tải phụ đề tiếng Việt...]"
        headers["Cache-Control"] = "no-store, no-cache, must-revalidate"

    vtt_text = vtt_content.strip()
    if not vtt_text.startswith("WEBVTT"):
        vtt_text = "WEBVTT\n\n" + vtt_text

    return Response(
        content=vtt_text.encode("utf-8"),
        media_type="text/vtt; charset=utf-8",
        headers=headers
    )

@moviesdrive_router.get("/moviesdrive/subtitles/{type}/{id}.json")
@moviesdrive_router.get("/moviesdrive/subtitles/{type}/{id}/{extra}.json")
@moviesdrive_router.get("/subtitles/{type}/{id}.json")
@moviesdrive_router.get("/subtitles/{type}/{id}/{extra}.json")
async def moviesdrive_subtitles(request: Request, type: str, id: str, extra: str = ""):
    """Serve matching subtitles with prioritized 100% synced Vietnamese AI track."""
    base_url = str(request.base_url).rstrip('/')
    clean_id = id.replace(":", "_").replace("/", "_")
    ai_sub_url = f"{base_url}/subtitles/vtt/{clean_id}.vtt?type={type}&orig_id={urllib.parse.quote(id)}"
    
    # Priority Synced Track (Instant 100% sync)
    subtitles_list = [
        {
            "id": f"vi_synced_{clean_id}",
            "url": ai_sub_url,
            "lang": "vie",
            "name": "🇻🇳 Tiếng Việt Đồng Bộ Chuẩn 100% (AI Instant)"
        }
    ]

    imdb_id = id
    if id.startswith("moviesdrive:"):
        resolved_imdb = await find_imdb_for_moviesdrive_id(type, id)
        if resolved_imdb:
            imdb_id = resolved_imdb

    if imdb_id and (imdb_id.startswith("tt") or ":" in imdb_id):
        url = f"https://opensubtitles-v3.strem.io/subtitles/{type}/{urllib.parse.quote(imdb_id)}.json"
        if extra:
            url = f"https://opensubtitles-v3.strem.io/subtitles/{type}/{urllib.parse.quote(imdb_id)}/{urllib.parse.quote(extra)}.json"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    subs = resp.json().get("subtitles", [])
                    subtitles_list.extend(subs)
        except Exception as e:
            logger.warning(f"Failed to fetch subtitles from OpenSubtitles for {imdb_id}: {e}")

    return JSONResponse(content={"subtitles": subtitles_list})

# ------------------------------------------------------------------
# Standalone Runner
# ------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="MoviesDrive Stremio Addon")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(moviesdrive_router)
    print("Starting MoviesDrive Stremio Addon at http://127.0.0.1:7004/moviesdrive/manifest.json")
    uvicorn.run(app, host="0.0.0.0", port=7004)
