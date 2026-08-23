import asyncio
import logging
import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from config import Config

logger = logging.getLogger(__name__)

movies2watch_router = APIRouter(prefix="", tags=["movies2watch"])

MOVIES2WATCH_BASE_URL = "https://movies2watch.vc"

# In-memory cache & client pool
_m2w_cache: Dict[str, Tuple[Any, float]] = {}
M2W_CACHE_TTL = 600  # 10 minutes

_m2w_client: Optional[httpx.AsyncClient] = None
_client_loop: Optional[asyncio.AbstractEventLoop] = None


def get_m2w_client() -> httpx.AsyncClient:
    global _m2w_client, _client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if (
        _m2w_client is None
        or _m2w_client.is_closed
        or _client_loop != current_loop
        or (current_loop and current_loop.is_closed())
    ):
        _client_loop = current_loop
        _m2w_client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=6.0),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=30, max_connections=60),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "https://movies2watch.vc/",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
    return _m2w_client


async def m2w_fetch_html(url: str, ttl: int = M2W_CACHE_TTL, referer: Optional[str] = None) -> Optional[str]:
    now = time.time()
    if url in _m2w_cache:
        data, exp = _m2w_cache[url]
        if now < exp:
            return data

    client = get_m2w_client()
    headers = {"Referer": referer or "https://movies2watch.vc/"}
    for attempt in range(2):
        try:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                html = res.text
                _m2w_cache[url] = (html, now + ttl)
                return html
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
            logger.error(f"Movies2Watch fetch failed for {url}: {e}")
            return None
    return None


# ------------------------------------------------------------------
# Genres & Countries Maps
# ------------------------------------------------------------------
GENRES_MAP = {
    "Action": "8",
    "Action & Adventure": "21",
    "Adventure": "9",
    "Animation": "17",
    "Comedy": "2",
    "Crime": "5",
    "Documentary": "13",
    "Drama": "1",
    "Family": "16",
    "Fantasy": "12",
    "History": "3",
    "Horror": "10",
    "Kids": "26",
    "Music": "18",
    "Musical": "25",
    "Mystery": "14",
    "News": "28",
    "Reality": "24",
    "Romance": "7",
    "Sci-Fi & Fantasy": "20",
    "Science Fiction": "15",
    "Soap": "27",
    "Talk": "23",
    "Thriller": "11",
    "TV Movie": "19",
    "War": "4",
    "War & Politics": "22",
    "Western": "6",
}

COUNTRIES_MAP = {
    "United States of America": "1",
    "United Kingdom": "6",
    "France": "4",
    "Canada": "25",
    "Japan": "10",
    "Germany": "2",
    "Italy": "18",
    "India": "12",
    "Spain": "26",
    "South Korea": "29",
    "Australia": "21",
    "Hong Kong": "27",
    "China": "58",
    "Belgium": "45",
    "Sweden": "3",
    "Mexico": "16",
    "Netherlands": "13",
    "Poland": "28",
    "Ireland": "34",
    "Denmark": "9",
    "Brazil": "30",
    "Turkey": "52",
    "Philippines": "19",
    "Argentina": "38",
    "Switzerland": "11",
    "Norway": "24",
    "Taiwan": "39",
    "Russia": "70",
}

GENRE_OPTIONS = list(GENRES_MAP.keys())
COUNTRY_OPTIONS = list(COUNTRIES_MAP.keys())
ALL_FILTER_OPTIONS = list(dict.fromkeys(GENRE_OPTIONS + COUNTRY_OPTIONS))


def get_movies2watch_manifest() -> Dict[str, Any]:
    from config import Config

    show_on_board = getattr(Config, "ENABLE_BOARD_MOVIES2WATCH", True)
    main_req = not show_on_board

    return {
        "id": "com.stremio.movies2watch.addon",
        "version": "1.0.0",
        "name": "Movies2Watch - Free Movies & TV Series HD",
        "description": "Watch Free Movies & TV Series from Movies2Watch (Full HD / Multi-Server / Subtitles)",
        "resources": [
            "catalog",
            {
                "name": "meta",
                "types": ["movie", "series"],
                "idPrefixes": ["movies2watch:", "m2w:"],
            },
            {
                "name": "stream",
                "types": ["movie", "series"],
                "idPrefixes": ["movies2watch:", "m2w:"],
            },
        ],
        "types": ["movie", "series"],
        "catalogs": [
            {
                "type": "movie",
                "id": "movies2watch_phim_moi_movie",
                "name": "Movies2Watch - Latest Movies",
                "extra": [
                    {
                        "name": "genre",
                        "options": ["Tất cả"] + ALL_FILTER_OPTIONS,
                        "isRequired": main_req,
                    },
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "type": "series",
                "id": "movies2watch_phim_moi_series",
                "name": "Movies2Watch - Latest TV Shows",
                "extra": [
                    {
                        "name": "genre",
                        "options": ["Tất cả"] + ALL_FILTER_OPTIONS,
                        "isRequired": main_req,
                    },
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "type": "movie",
                "id": "movies2watch_trending",
                "name": "Movies2Watch - Trending & Home",
                "extra": [
                    {
                        "name": "genre",
                        "options": ["Tất cả"] + ALL_FILTER_OPTIONS,
                        "isRequired": main_req,
                    },
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
        ],
    }


# ------------------------------------------------------------------
# Manifest Route
# ------------------------------------------------------------------
@movies2watch_router.get("/movies2watch/manifest.json")
@movies2watch_router.get("/manifest.json")
async def movies2watch_manifest():
    return JSONResponse(
        content=get_movies2watch_manifest(),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )


# ------------------------------------------------------------------
# Catalog Parser Helpers
# ------------------------------------------------------------------
def parse_m2w_cards(html: str) -> List[Dict[str, Any]]:
    metas = []
    if not html:
        return metas

    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(".flw-item")

    for item in items:
        try:
            # 1. Title & URL
            name_el = item.select_one(".film-name a")
            if not name_el:
                name_el = item.select_one(".film-poster a")
            if not name_el:
                continue

            title = name_el.text.strip()
            href = name_el.get("href", "")
            if not href:
                continue

            # Extract slug and media type
            # Examples:
            # https://movies2watch.vc/movie/oppenheimer-51311/ -> type=movie, slug=oppenheimer-51311
            # https://movies2watch.vc/series/avatar-the-last-airbender-67006/ -> type=series, slug=avatar-the-last-airbender-67006
            m_match = re.search(r"/(movie|series|tv)/([^/]+)", href)
            if not m_match:
                continue

            m_type = "movie" if m_match.group(1) == "movie" else "series"
            slug_id = m_match.group(2)

            # 2. Poster
            poster_el = item.select_one(".film-poster-img, img")
            poster = ""
            if poster_el:
                poster = poster_el.get("data-src") or poster_el.get("src") or ""

            # 3. Quality & Info
            info_el = item.select_one(".film-infor, .fd-infor")
            info_text = info_el.text.strip() if info_el else ""
            year_match = re.search(r"\b(19\d\d|20\d\d)\b", info_text)
            release_year = year_match.group(1) if year_match else ""

            metas.append(
                {
                    "id": f"movies2watch:{m_type}:{slug_id}",
                    "type": m_type,
                    "name": title,
                    "poster": poster,
                    "posterShape": "poster",
                    "releaseInfo": release_year,
                    "description": f"{title} ({release_year}) - Xem HD trên Movies2Watch",
                }
            )
        except Exception as e:
            logger.debug(f"Error parsing card: {e}")
            continue

    return metas


# ------------------------------------------------------------------
# Catalog Handler
# ------------------------------------------------------------------
@movies2watch_router.get("/movies2watch/catalog/{type}/{id}.json")
@movies2watch_router.get("/movies2watch/catalog/{type}/{id}/{extra:path}")
@movies2watch_router.get("/catalog/{type}/{id}.json")
@movies2watch_router.get("/catalog/{type}/{id}/{extra:path}")
async def movies2watch_catalog_handler(
    type: str,
    id: str,
    extra: Optional[str] = None,
    genre: Optional[str] = None,
    search: Optional[str] = None,
    skip: Optional[int] = None,
):
    from config import Config

    if not getattr(Config, "ENABLE_SOURCE_MOVIES2WATCH", True):
        return {"metas": []}

    base_url = getattr(Config, "MOVIES2WATCH_BASE_URL", MOVIES2WATCH_BASE_URL).rstrip("/")

    search_val = search
    genre_val = genre
    skip_val = skip or 0

    if extra:
        extra_clean = extra.rstrip(".json") if extra.endswith(".json") else extra
        parsed_params = urllib.parse.parse_qs(extra_clean)
        if "search" in parsed_params:
            search_val = parsed_params["search"][0]
        if "genre" in parsed_params:
            genre_val = parsed_params["genre"][0]
        if "skip" in parsed_params:
            try:
                skip_val = int(parsed_params["skip"][0])
            except ValueError:
                pass

    page = (skip_val // 24) + 1

    try:
        # 1. Search flow
        if search_val:
            query = search_val.replace(" ", "-")
            url = f"{base_url}/search/{urllib.parse.quote(query)}"
            html = await m2w_fetch_html(url, ttl=300)
            metas = parse_m2w_cards(html or "")
            if type in ["movie", "series"]:
                metas = [m for m in metas if m.get("type") == type]
            return {"metas": metas}

        # 2. Filter flow (Genre or Country)
        if genre_val and genre_val not in ["Tất cả", "All"]:
            m_type_filter = "movie" if type == "movie" else "series"
            if genre_val in GENRES_MAP:
                g_code = GENRES_MAP[genre_val]
                url = f"{base_url}/filter.php?type={m_type_filter}&genre={g_code}&page={page}"
            elif genre_val in COUNTRIES_MAP:
                c_code = COUNTRIES_MAP[genre_val]
                url = f"{base_url}/filter.php?type={m_type_filter}&country={c_code}&page={page}"
            else:
                url = f"{base_url}/filter.php?type={m_type_filter}&keyword={urllib.parse.quote(genre_val)}&page={page}"

            html = await m2w_fetch_html(url, ttl=600)
            metas = parse_m2w_cards(html or "")
            return {"metas": metas}

        # 3. Standard Catalogs
        if id == "movies2watch_trending":
            url = f"{base_url}/home/"
        elif type == "movie" or id == "movies2watch_phim_moi_movie":
            url = f"{base_url}/movies?page={page}" if page > 1 else f"{base_url}/movies/"
        else:
            url = f"{base_url}/tv-series?page={page}" if page > 1 else f"{base_url}/tv-series/"

        html = await m2w_fetch_html(url, ttl=600)
        metas = parse_m2w_cards(html or "")
        return {"metas": metas}

    except Exception as e:
        logger.error(f"Error fetching Movies2Watch catalog for {id}: {e}")
        return {"metas": []}


# ------------------------------------------------------------------
# Meta Handler
# ------------------------------------------------------------------
@movies2watch_router.get("/movies2watch/meta/{type}/{id}.json")
@movies2watch_router.get("/meta/{type}/{id}.json")
async def movies2watch_meta_handler(type: str, id: str):
    from config import Config

    if not getattr(Config, "ENABLE_SOURCE_MOVIES2WATCH", True):
        return {"meta": {}}

    base_url = getattr(Config, "MOVIES2WATCH_BASE_URL", MOVIES2WATCH_BASE_URL).rstrip("/")

    parts = id.split(":")
    # formats:
    # movies2watch:movie:oppenheimer-51311
    # movies2watch:series:avatar-the-last-airbender-67006
    m_type = parts[1] if len(parts) > 1 else type
    slug_id = parts[2] if len(parts) > 2 else id

    url_path = "movie" if m_type == "movie" else "series"
    url = f"{base_url}/{url_path}/{slug_id}/"

    try:
        html = await m2w_fetch_html(url, ttl=1800)
        if not html:
            return {"meta": {}}

        soup = BeautifulSoup(html, "html.parser")

        # Name / Title
        name = ""
        heading_el = soup.select_one("h2.heading-name a, h2.heading-name, .heading-name")
        if heading_el:
            name = heading_el.text.strip()
        if not name:
            name = slug_id.replace("-", " ").title()

        # Poster
        poster = ""
        poster_el = soup.select_one(".film-poster-img, .poster img")
        if poster_el:
            poster = poster_el.get("src") or poster_el.get("data-src") or ""

        # Backdrop
        backdrop = poster
        bg_el = soup.select_one(".cover_follow, .w-cover")
        if bg_el and "background-image" in bg_el.get("style", ""):
            bg_m = re.search(r"url\(['\"]?([^'\")]+)['\"]?\)", bg_el["style"])
            if bg_m:
                backdrop = bg_m.group(1)

        # Overview / Description
        description = ""
        desc_el = soup.select_one(".description, .film-description")
        if desc_el:
            description = desc_el.text.strip()

        # Genres
        genres = []
        for g_a in soup.select('.elements .row-line a[href*="genre"], .film-genres a'):
            g_text = g_a.text.strip()
            if g_text and g_text not in genres:
                genres.append(g_text)

        # Release Info & Rating
        release_info = ""
        year_m = re.search(r"Released:\s*(\d{4})", html)
        if year_m:
            release_info = year_m.group(1)
        else:
            y_find = re.search(r"\b(19\d\d|20\d\d)\b", html)
            if y_find:
                release_info = y_find.group(1)

        videos = []
        if m_type == "series":
            # Extract seasons from dropdown
            ss_items = soup.select("a.ss-item")
            client = get_m2w_client()

            for s_item in ss_items:
                s_num_str = s_item.get("data-ss")
                s_token = s_item.get("data-id")
                try:
                    s_num = int(s_num_str) if s_num_str else 1
                except ValueError:
                    s_num = 1

                if s_token:
                    # Fetch episodes for this season
                    ep_url = f"{base_url}/ajax/ajax.php?episode={urllib.parse.quote(s_token, safe='')}"
                    ep_html = await m2w_fetch_html(ep_url, ttl=1800, referer=url)
                    if ep_html:
                        ep_soup = BeautifulSoup(ep_html, "html.parser")
                        for ep_item in ep_soup.select("a.eps-item, a.nav-link"):
                            ep_title = ep_item.get("title") or ep_item.text.strip()
                            ep_href = ep_item.get("href", "")
                            
                            # Extract episode number
                            ep_num = len(videos) + 1
                            href_m = re.search(r"/(\d+)-(\d+)/?", ep_href)
                            if href_m:
                                ep_num = int(href_m.group(2))
                            else:
                                num_m = re.search(r"Episode\s*(\d+)", ep_title, re.IGNORECASE)
                                if num_m:
                                    ep_num = int(num_m.group(1))

                            videos.append(
                                {
                                    "id": f"movies2watch:series:{slug_id}:{s_num}:{ep_num}",
                                    "title": f"S{s_num}E{ep_num}: {ep_title}",
                                    "season": s_num,
                                    "episode": ep_num,
                                    "released": release_info,
                                }
                            )

        meta = {
            "id": f"movies2watch:{m_type}:{slug_id}",
            "type": m_type,
            "name": name,
            "poster": poster,
            "background": backdrop,
            "description": description,
            "genres": genres,
            "releaseInfo": release_info[:4] if release_info else "",
            "videos": videos if m_type == "series" else [],
        }

        return {"meta": meta}
    except Exception as e:
        logger.error(f"Error fetching Movies2Watch meta for {id}: {e}")
        return {"meta": {}}


# ------------------------------------------------------------------
# Stream Resolver Helpers
# ------------------------------------------------------------------
async def resolve_vixsrc_from_url(embed_url: str) -> Optional[Tuple[str, str, Dict[str, str]]]:
    """Resolve VixSrc / VixCloud embed URL to direct HLS master playlist URL and headers."""
    try:
        client = get_m2w_client()
        m_match = re.search(r"vixsrc\.to/(movie|tv)/([0-9]+)(?:/([0-9]+)/([0-9]+))?", embed_url)
        if not m_match:
            return None

        kind = m_match.group(1)
        tmdb_id = m_match.group(2)
        season = m_match.group(3)
        episode = m_match.group(4)

        if kind == "movie":
            api_url = f"https://vixsrc.to/api/movie/{tmdb_id}"
        else:
            api_url = f"https://vixsrc.to/api/tv/{tmdb_id}/{season or 1}/{episode or 1}"

        api_res = await client.get(api_url, headers={"Referer": embed_url, "Origin": "https://vixsrc.to"})
        if api_res.status_code != 200:
            return None

        api_data = api_res.json()
        src_path = api_data.get("src")
        if not src_path:
            return None

        embed_page_url = f"https://vixsrc.to{src_path}" if src_path.startswith("/") else src_path
        embed_html_res = await client.get(embed_page_url, headers={"Referer": embed_url})
        if embed_html_res.status_code != 200:
            return None

        embed_html = embed_html_res.text
        token_m = re.search(r"['\"]token['\"]\s*:\s*['\"]([^'\"]+)['\"]", embed_html)
        expires_m = re.search(r"['\"]expires['\"]\s*:\s*['\"]([^'\"]+)['\"]", embed_html)
        url_m = re.search(r"url:\s*['\"](https://[^'\"]+)['\"]", embed_html)

        if token_m and expires_m and url_m:
            token = token_m.group(1)
            expires = expires_m.group(1)
            pl_base = url_m.group(1)
            m3u8_url = f"{pl_base}?token={token}&expires={expires}&h=1&lang=en"
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": embed_page_url,
                "Origin": "https://vixsrc.to",
            }
            return m3u8_url, embed_page_url, headers

        return None
    except Exception as e:
        logger.warning(f"Failed to resolve VixSrc stream for {embed_url}: {e}")
        return None


# ------------------------------------------------------------------
# Stream Handler
# ------------------------------------------------------------------
@movies2watch_router.get("/movies2watch/stream/{type}/{id}.json")
@movies2watch_router.get("/stream/{type}/{id}.json")
async def movies2watch_stream_handler(request: Request, type: str, id: str):
    from config import Config

    if not getattr(Config, "ENABLE_SOURCE_MOVIES2WATCH", True):
        return {"streams": []}

    base_url = getattr(Config, "MOVIES2WATCH_BASE_URL", MOVIES2WATCH_BASE_URL).rstrip("/")
    app_base_url = (
        Config.ADDON_URL.rstrip("/")
        if getattr(Config, "ADDON_URL", None) and not Config.ADDON_URL.startswith("http://localhost")
        else str(request.base_url).rstrip("/")
    )

    parts = id.split(":")
    # formats:
    # movies2watch:movie:oppenheimer-51311
    # movies2watch:series:avatar-the-last-airbender-67006:1:1
    m_type = parts[1] if len(parts) > 1 else type
    slug_id = parts[2] if len(parts) > 2 else id
    season = int(parts[3]) if len(parts) >= 4 and parts[3].isdigit() else 1
    episode = int(parts[4]) if len(parts) >= 5 and parts[4].isdigit() else 1

    streams = []

    try:
        client = get_m2w_client()

        # Step 1: Fetch details / episode page to extract pl_url
        if m_type == "series":
            page_url = f"{base_url}/series/{slug_id}/{season}-{episode}/"
        else:
            page_url = f"{base_url}/movie/{slug_id}/"

        page_html = await m2w_fetch_html(page_url, ttl=600)
        if not page_html:
            return {"streams": []}

        # Step 2: Extract pl_url
        pl_match = re.search(r"const pl_url = ['\"]([^'\"]+)['\"]", page_html)
        if not pl_match:
            return {"streams": []}

        pl_url = pl_match.group(1)
        servers_res = await client.get(pl_url, headers={"Referer": page_url})
        if servers_res.status_code != 200:
            return {"streams": []}

        servers_soup = BeautifulSoup(servers_res.text, "html.parser")
        server_links = servers_soup.select("a.sv-item, a[data-srv]")

        found_imdb_id: Optional[str] = None
        found_tmdb_id: Optional[str] = None

        for link_el in server_links:
            server_name = link_el.get("data-srv") or link_el.get("title") or "Server"
            embed_url = link_el.get("data-id") or ""
            if not embed_url or not embed_url.startswith("http"):
                continue

            # Extract IMDb / TMDB IDs from embed URLs if present
            # Examples:
            # https://0123movie.space/mv/tt15398776/872585/
            # https://0123movie.space/pl/82452/1/1/
            # https://player.videasy.net/movie/872585
            # https://vidsrc.cc/v2/embed/movie/tt15398776
            # https://vidfast.pro/movie/tt15398776
            imdb_m = re.search(r"(tt\d+)", embed_url)
            if imdb_m and not found_imdb_id:
                found_imdb_id = imdb_m.group(1)

            tmdb_m = re.search(r"/movie/(\d+)|/tv/(\d+)|/(\d{4,8})/", embed_url)
            if tmdb_m and not found_tmdb_id:
                found_tmdb_id = tmdb_m.group(1) or tmdb_m.group(2) or tmdb_m.group(3)

            # Check for direct VixSrc resolver
            if "vixsrc.to" in embed_url or "vixcloud" in embed_url:
                resolved = await resolve_vixsrc_from_url(embed_url)
                if resolved:
                    m3u8_url, embed_ref, req_headers = resolved
                    proxy_endpoint = (
                        f"{app_base_url}/movies2watch/stream_proxy"
                        if not app_base_url.endswith("/movies2watch")
                        else f"{app_base_url}/stream_proxy"
                    )
                    proxy_stream_url = (
                        f"{proxy_endpoint}"
                        f"?url={urllib.parse.quote(m3u8_url, safe='')}"
                        f"&referer={urllib.parse.quote(embed_ref, safe='')}"
                    )
                    streams.append(
                        {
                            "name": f"Movies2Watch [{server_name}]",
                            "title": (
                                f"▶ Phát Trực Tiếp Stremio [{server_name}]\n"
                                f"🎬 Movies2Watch HLS Full HD / Multi-Audio\n"
                                f"⚡ Máy chủ tốc độ cao, hỗ trợ phụ đề"
                            ),
                            "url": proxy_stream_url,
                            "behaviorHints": {
                                "notSupported": False,
                                "requestHeaders": req_headers,
                            },
                        }
                    )
                    continue

        # Step 3: Check if TMDB ID / IMDb ID is present, or resolve via TMDB search
        title_clean = slug_id.replace("-", " ").title()
        year_str = ""
        heading_el = BeautifulSoup(page_html, "html.parser").select_one("h2.heading-name a, h2.heading-name")
        if heading_el:
            title_clean = heading_el.text.strip()
        y_m = re.search(r"Released:\s*(\d{4})", page_html)
        if y_m:
            year_str = y_m.group(1)

        if not found_tmdb_id:
            try:
                from vidking_router import vidking_fetch_tmdb_json
                clean_q = re.sub(r"-\d+$", "", slug_id).replace("-", " ")
                tmdb_type = "movie" if m_type == "movie" else "tv"
                params = {"query": clean_q}
                if year_str:
                    params["year" if tmdb_type == "movie" else "first_air_date_year"] = year_str
                s_data = await vidking_fetch_tmdb_json(f"/search/{tmdb_type}", params=params, ttl=3600)
                results = s_data.get("results", []) if s_data else []
                if results:
                    found_tmdb_id = str(results[0]["id"])
                    if not year_str and (results[0].get("release_date") or results[0].get("first_air_date")):
                        year_str = (results[0].get("release_date") or results[0].get("first_air_date"))[:4]
            except Exception as e:
                logger.debug(f"TMDB search fallback error: {e}")

        # Step 4: Generate high-speed HLS & MP4 direct streams via Vidking Multi-Server Engine
        if found_tmdb_id and str(found_tmdb_id).isdigit():
            try:
                from vidking_router import (
                    VIDKING_SERVERS,
                    fetch_and_decrypt_server,
                    get_vidking_seed,
                )

                tmdb_int = int(found_tmdb_id)
                media_t = "tv" if m_type == "series" else "movie"
                seed = await get_vidking_seed(tmdb_int)
                if seed:
                    tasks = [
                        fetch_and_decrypt_server(
                            server_cfg=srv,
                            tmdb_id=tmdb_int,
                            media_type=media_t,
                            title=title_clean,
                            year=year_str,
                            imdb_id=found_imdb_id or "",
                            season=season,
                            episode=episode,
                            seed=seed,
                            base_url=app_base_url,
                        )
                        for srv in VIDKING_SERVERS
                    ]
                    srv_results = await asyncio.gather(*tasks, return_exceptions=True)
                    for r_list in srv_results:
                        if isinstance(r_list, list):
                            for s_item in r_list:
                                orig_name = s_item.get("name", "")
                                # Enhance badge with Movies2Watch [Videasy] branding
                                if "2160" in orig_name:
                                    s_item["name"] = orig_name.replace("Vidking", "Movies2Watch [Videasy] 💎")
                                else:
                                    s_item["name"] = orig_name.replace("Vidking", "Movies2Watch [Videasy]")
                                streams.append(s_item)
            except Exception as e:
                logger.warning(f"Vidking direct stream resolution failed for TMDB {found_tmdb_id}: {e}")

        # Step 5: Direct VixSrc Resolver if tmdb_id is available
        if found_tmdb_id and str(found_tmdb_id).isdigit():
            try:
                vix_url = (
                    f"https://vixsrc.to/tv/{found_tmdb_id}/{season}/{episode}"
                    if m_type == "series"
                    else f"https://vixsrc.to/movie/{found_tmdb_id}"
                )
                resolved = await resolve_vixsrc_from_url(vix_url)
                if resolved:
                    m3u8_url, embed_ref, req_headers = resolved
                    proxy_endpoint = (
                        f"{app_base_url}/movies2watch/stream_proxy"
                        if not app_base_url.endswith("/movies2watch")
                        else f"{app_base_url}/stream_proxy"
                    )
                    proxy_stream_url = (
                        f"{proxy_endpoint}"
                        f"?url={urllib.parse.quote(m3u8_url, safe='')}"
                        f"&referer={urllib.parse.quote(embed_ref, safe='')}"
                    )
                    streams.append(
                        {
                            "name": "Movies2Watch ⚡ VixSrc\n1080p FHD",
                            "title": (
                                f"🎬 {title_clean} {f'S{season:02d}E{episode:02d}' if m_type == 'series' else ''}\n"
                                f"▶ Phát Trực Tiếp Stremio [VixSrc HLS Full HD]\n"
                                f"🌐 Đa âm thanh & Đa phụ đề (Multi-Audio & Multi-Sub)\n"
                                f"⚡ Trình phát mặc định Stremio (LibVLC/ExoPlayer)"
                            ),
                            "url": proxy_stream_url,
                            "behaviorHints": {
                                "notSupported": False,
                                "requestHeaders": req_headers,
                            },
                        }
                    )
            except Exception as e:
                logger.debug(f"VixSrc resolution error: {e}")

        # Step 6: External Web Embed Player Fallbacks
        for link_el in server_links:
            server_name = link_el.get("data-srv") or link_el.get("title") or "Server"
            embed_url = link_el.get("data-id") or ""
            if not embed_url or not embed_url.startswith("http"):
                continue

            streams.append(
                {
                    "name": f"Movies2Watch\n🌐 {server_name}",
                    "title": (
                        f"🎬 {title_clean} {f'S{season:02d}E{episode:02d}' if m_type == 'series' else ''}\n"
                        f"🌐 Xem Trình Duyệt Web [Server: {server_name}]\n"
                        f"🚀 0% Băng thông máy chủ | Nhấp để mở trên web"
                    ),
                    "externalUrl": embed_url,
                }
            )

        # Step 7: Sort streams by quality priority (2160p 4K first, then 1080p, 720p, etc.)
        def _stream_sort_key(item: Dict[str, Any]) -> int:
            name_str = (item.get("name") or "").lower()
            title_str = (item.get("title") or "").lower()
            if "2160" in name_str or "4k" in name_str or "2160" in title_str:
                return 4000
            if "1080" in name_str or "fhd" in name_str or "1080" in title_str:
                return 2000
            if "720" in name_str or "hd" in name_str or "720" in title_str:
                return 1000
            if "480" in name_str or "sd" in name_str or "480" in title_str:
                return 500
            if "externalurl" in item:
                return 50
            return 100

        streams = sorted(streams, key=_stream_sort_key, reverse=True)
        return {"streams": streams}

    except Exception as e:
        logger.error(f"Error fetching Movies2Watch streams for {id}: {e}")
        return {"streams": []}


# ------------------------------------------------------------------
# Stream Proxy Handler (Range Requests & M3U8 Stream Proxying)
# ------------------------------------------------------------------
@movies2watch_router.get("/movies2watch/stream_proxy")
@movies2watch_router.get("/stream_proxy")
async def movies2watch_stream_proxy(
    request: Request,
    url: str,
    referer: Optional[str] = None,
):
    """Proxies HLS stream playlists and chunks with proper Referer and Range headers."""
    if not url:
        raise HTTPException(status_code=400, detail="Missing stream URL")

    client = get_m2w_client()
    req_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }
    if referer:
        req_headers["Referer"] = referer

    range_header = request.headers.get("Range")
    if range_header:
        req_headers["Range"] = range_header

    try:
        upstream_req = client.build_request("GET", url, headers=req_headers)
        upstream_res = await client.send(upstream_req, stream=True)

        resp_headers = {}
        for h_name in ["Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"]:
            if h_name in upstream_res.headers:
                resp_headers[h_name] = upstream_res.headers[h_name]

        resp_headers["Access-Control-Allow-Origin"] = "*"
        resp_headers["Access-Control-Allow-Headers"] = "*"

        async def stream_generator():
            try:
                async for chunk in upstream_res.aiter_bytes(chunk_size=65536):
                    yield chunk
            finally:
                await upstream_res.aclose()

        return StreamingResponse(
            stream_generator(),
            status_code=upstream_res.status_code,
            headers=resp_headers,
            media_type=upstream_res.headers.get("Content-Type", "application/vnd.apple.mpegurl"),
        )
    except Exception as e:
        logger.error(f"Movies2Watch stream proxy error for {url}: {e}")
        raise HTTPException(status_code=502, detail=f"Proxy error: {e}")
