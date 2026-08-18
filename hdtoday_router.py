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

logger = logging.getLogger(__name__)

hdtoday_router = APIRouter(prefix="", tags=["hdtoday"])

HDTODAY_BASE_URL = "https://hdtoday.sc"

# In-memory cache & client pool
_hdtoday_cache: Dict[str, Tuple[Any, float]] = {}
HDTODAY_CACHE_TTL = 600  # 10 minutes

_hdtoday_client: Optional[httpx.AsyncClient] = None
_client_loop: Optional[asyncio.AbstractEventLoop] = None


def get_hdtoday_client() -> httpx.AsyncClient:
    global _hdtoday_client, _client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if (
        _hdtoday_client is None
        or _hdtoday_client.is_closed
        or _client_loop != current_loop
        or (current_loop and current_loop.is_closed())
    ):
        _client_loop = current_loop
        _hdtoday_client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=6.0),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=30, max_connections=60),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": "https://hdtoday.sc/",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
    return _hdtoday_client


async def hdtoday_fetch_html(url: str, ttl: int = HDTODAY_CACHE_TTL) -> Optional[str]:
    now = time.time()
    if url in _hdtoday_cache:
        data, exp = _hdtoday_cache[url]
        if now < exp:
            return data

    client = get_hdtoday_client()
    for attempt in range(2):
        try:
            res = await client.get(url)
            if res.status_code == 200:
                html = res.text
                _hdtoday_cache[url] = (html, now + ttl)
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
            logger.error(f"HDToday fetch failed for {url}: {e}")
            return None
    return None


async def hdtoday_fetch_json(url: str, ttl: int = HDTODAY_CACHE_TTL) -> Optional[dict]:
    now = time.time()
    if url in _hdtoday_cache:
        data, exp = _hdtoday_cache[url]
        if now < exp:
            return data

    client = get_hdtoday_client()
    for attempt in range(2):
        try:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json()
                _hdtoday_cache[url] = (data, now + ttl)
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
            logger.error(f"HDToday fetch json failed for {url}: {e}")
            return None
    return None


# ------------------------------------------------------------------
# Genres & Countries Maps
# ------------------------------------------------------------------
GENRES_MAP = {
    "Action": "action",
    "Action & Adventure": "action-adventure",
    "Adventure": "adventure",
    "Animation": "animation",
    "Comedy": "comedy",
    "Crime": "crime",
    "Documentary": "documentary",
    "Drama": "drama",
    "Family": "family",
    "Fantasy": "fantasy",
    "History": "history",
    "Horror": "horror",
    "Kids": "kids",
    "Music": "music",
    "Mystery": "mystery",
    "News": "news",
    "Reality": "reality",
    "Romance": "romance",
    "Sci-Fi & Fantasy": "sci-fi-fantasy",
    "Science Fiction": "science-fiction",
    "Soap": "soap",
    "Talk": "talk",
    "Thriller": "thriller",
    "TV Movie": "tv-movie",
    "War": "war",
    "War & Politics": "war-politics",
    "Western": "western",
}

COUNTRIES_MAP = {
    "United States of America": "us",
    "United Kingdom": "gb",
    "Japan": "jp",
    "South Korea": "kr",
    "France": "fr",
    "Germany": "de",
    "Canada": "ca",
    "Australia": "au",
    "China": "cn",
    "Hong Kong": "hk",
    "Taiwan": "tw",
    "Thailand": "th",
    "India": "in",
    "Spain": "es",
    "Italy": "it",
    "Brazil": "br",
    "Mexico": "mx",
    "Russia": "ru",
    "Netherlands": "nl",
    "Sweden": "se",
    "Norway": "no",
    "Denmark": "dk",
    "Belgium": "be",
    "Switzerland": "ch",
    "Austria": "at",
    "Poland": "pl",
    "New Zealand": "nz",
    "South Africa": "za",
}

GENRE_OPTIONS = list(GENRES_MAP.keys())
COUNTRY_OPTIONS = list(COUNTRIES_MAP.keys())
ALL_FILTER_OPTIONS = list(dict.fromkeys(GENRE_OPTIONS + COUNTRY_OPTIONS))


def get_hdtoday_manifest() -> Dict[str, Any]:
    from config import Config

    show_on_board = getattr(Config, "ENABLE_BOARD_HDTODAY", True)
    main_req = not show_on_board

    return {
        "id": "com.stremio.hdtoday.addon",
        "version": "1.0.0",
        "name": "HDToday - Movies & TV Series HD",
        "description": "Watch Free Movies & TV Series from HDToday (Full HD / Multi-Audio & Subtitles)",
        "resources": [
            "catalog",
            {
                "name": "meta",
                "types": ["movie", "series"],
                "idPrefixes": ["hdtoday:"],
            },
            {
                "name": "stream",
                "types": ["movie", "series"],
                "idPrefixes": ["hdtoday:"],
            },
        ],
        "types": ["movie", "series"],
        "catalogs": [
            {
                "type": "movie",
                "id": "hdtoday_phim_moi_movie",
                "name": "HDToday - Latest Movies",
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
                "id": "hdtoday_phim_moi_series",
                "name": "HDToday - Latest TV Shows",
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
                "id": "hdtoday_top_imdb",
                "name": "HDToday - Top IMDb",
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
                "id": "hdtoday_the_loai",
                "name": "HDToday - Movies by Genre",
                "extra": [
                    {"name": "genre", "options": GENRE_OPTIONS, "isRequired": True},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "type": "series",
                "id": "hdtoday_the_loai_series",
                "name": "HDToday - Series by Genre",
                "extra": [
                    {"name": "genre", "options": GENRE_OPTIONS, "isRequired": True},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "type": "movie",
                "id": "hdtoday_quoc_gia",
                "name": "HDToday - Movies by Country",
                "extra": [
                    {"name": "genre", "options": COUNTRY_OPTIONS, "isRequired": True},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "type": "series",
                "id": "hdtoday_quoc_gia_series",
                "name": "HDToday - Series by Country",
                "extra": [
                    {"name": "genre", "options": COUNTRY_OPTIONS, "isRequired": True},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
        ],
    }


@hdtoday_router.get("/hdtoday/manifest.json")
@hdtoday_router.get("/manifest.json")
async def get_manifest():
    return JSONResponse(get_hdtoday_manifest())


# ------------------------------------------------------------------
# Catalog Parser
# ------------------------------------------------------------------
def parse_flw_items(html: str, target_type: str = "movie") -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(".flw-item")
    metas = []

    for item in items:
        a_href = item.select_one(".film-poster-ahref, .film-detail a")
        if not a_href:
            continue
        href = a_href.get("href", "")
        if not href:
            continue

        # e.g. /movie/avatar-7yeqHJL09WY or /tv/the-legend-of-korra-EOX7CgngyYz
        m_type = "series" if "/tv/" in href else "movie"
        slug_id = href.rstrip("/").split("/")[-1]

        title_el = item.select_one(".film-name a")
        title = title_el.text.strip() if title_el else a_href.get("title", "Unknown")

        img_el = item.select_one(".film-poster img")
        poster = ""
        if img_el:
            poster = (
                img_el.get("data-src")
                or img_el.get("src")
                or img_el.get("data-original")
                or ""
            )

        fdi_items = [f.text.strip() for f in item.select(".fdi-item")]
        desc_info = " | ".join(fdi_items) if fdi_items else ""

        metas.append(
            {
                "id": f"hdtoday:{m_type}:{slug_id}",
                "type": m_type,
                "name": title,
                "poster": poster,
                "description": desc_info or "HDToday HD Stream",
            }
        )

    return metas


# ------------------------------------------------------------------
# Catalog Handler
# ------------------------------------------------------------------
@hdtoday_router.get("/hdtoday/catalog/{type}/{id}.json")
@hdtoday_router.get("/hdtoday/catalog/{type}/{id}/{extra}.json")
@hdtoday_router.get("/catalog/{type}/{id}.json")
@hdtoday_router.get("/catalog/{type}/{id}/{extra}.json")
async def hdtoday_catalog_handler(
    type: str, id: str, extra: Optional[str] = None
):
    from config import Config

    base_url = getattr(Config, "HDTODAY_BASE_URL", HDTODAY_BASE_URL).rstrip("/")

    skip = 0
    search_keyword = None
    genre_val = None

    if extra:
        pairs = extra.split("&")
        for p in pairs:
            if "=" in p:
                k, v = p.split("=", 1)
                v = urllib.parse.unquote(v)
                if k == "skip":
                    try:
                        skip = int(v)
                    except ValueError:
                        skip = 0
                elif k == "search":
                    search_keyword = v.strip()
                elif k == "genre":
                    genre_val = v.strip()

    page = (skip // 32) + 1

    if search_keyword:
        kw = urllib.parse.quote(search_keyword)
        page_url = f"{base_url}/search/{kw}?page={page}"
    elif genre_val and genre_val != "Tất cả":
        if genre_val in GENRES_MAP:
            g_slug = GENRES_MAP[genre_val]
            page_url = f"{base_url}/genre/{g_slug}?page={page}"
        elif genre_val in COUNTRIES_MAP:
            c_slug = COUNTRIES_MAP[genre_val]
            page_url = f"{base_url}/country/{c_slug}?page={page}"
        else:
            page_url = f"{base_url}/movie?page={page}"
    elif id == "hdtoday_phim_moi_series":
        page_url = f"{base_url}/tv-show?page={page}"
    elif id == "hdtoday_top_imdb":
        page_url = f"{base_url}/top-imdb?page={page}"
    elif id in ["hdtoday_the_loai", "hdtoday_the_loai_series"]:
        page_url = f"{base_url}/genre/action?page={page}"
    elif id in ["hdtoday_quoc_gia", "hdtoday_quoc_gia_series"]:
        page_url = f"{base_url}/country/us?page={page}"
    else:
        page_url = f"{base_url}/movie?page={page}"

    try:
        html = await hdtoday_fetch_html(page_url, ttl=300)
        if not html:
            return {"metas": []}

        metas = parse_flw_items(html, target_type=type)
        return {"metas": metas}
    except Exception as e:
        logger.error(f"Error fetching HDToday catalog {id}: {e}")
        return {"metas": []}


# ------------------------------------------------------------------
# Meta Handler
# ------------------------------------------------------------------
@hdtoday_router.get("/hdtoday/meta/{type}/{id}.json")
@hdtoday_router.get("/meta/{type}/{id}.json")
async def hdtoday_meta_handler(type: str, id: str):
    from config import Config

    base_url = getattr(Config, "HDTODAY_BASE_URL", HDTODAY_BASE_URL).rstrip("/")

    parts = id.split(":")
    if len(parts) >= 3:
        m_type = parts[1]
        slug_id = parts[2]
    elif len(parts) == 2:
        m_type = type
        slug_id = parts[1]
    else:
        m_type = type
        slug_id = id

    page_path = "tv" if m_type == "series" else "movie"
    detail_url = f"{base_url}/{page_path}/{slug_id}"

    try:
        html = await hdtoday_fetch_html(detail_url, ttl=600)
        if not html:
            return {"meta": {}}

        soup = BeautifulSoup(html, "html.parser")
        title_el = soup.select_one(".heading-name a, h2.heading-name")
        name = title_el.text.strip() if title_el else slug_id

        desc_el = soup.select_one(".description")
        description = desc_el.text.strip() if desc_el else ""

        poster_el = soup.select_one(".film-poster img")
        poster = ""
        if poster_el:
            poster = (
                poster_el.get("data-src")
                or poster_el.get("src")
                or poster_el.get("data-original")
                or ""
            )

        backdrop_el = soup.select_one(".cover_follow")
        backdrop = poster
        if backdrop_el and "background-image" in backdrop_el.get("style", ""):
            b_match = re.search(r"url\((['\"]?)(.*?)\1\)", backdrop_el["style"])
            if b_match:
                backdrop = b_match.group(2)

        # Parse element details
        genres = []
        release_info = ""
        for row in soup.select(".elements .row-line"):
            type_span = row.select_one(".type")
            if not type_span:
                continue
            label = type_span.text.strip().replace(":", "").lower()
            val = row.text.replace(type_span.text, "").strip()
            if "released" in label:
                release_info = val
            elif "genre" in label:
                genres = [
                    g.strip() for g in re.split(r"[,\n\r]+", val) if g.strip()
                ]

        watch_div = soup.select_one(".detail_page-watch")
        data_id = watch_div.get("data-id") if watch_div else ""

        videos = []
        if m_type == "series" and data_id:
            # Fetch seasons list
            seasons_html = await hdtoday_fetch_html(
                f"{base_url}/ajax/season/list/{data_id}", ttl=600
            )
            if seasons_html:
                s_soup = BeautifulSoup(seasons_html, "html.parser")
                season_items = s_soup.select(".dropdown-item")

                for s_idx, s_item in enumerate(season_items, start=1):
                    s_id = s_item.get("data-id")
                    s_title = s_item.text.strip()
                    s_num_match = re.search(r"\d+", s_title)
                    s_num = int(s_num_match.group(0)) if s_num_match else s_idx

                    # Fetch episodes for this season
                    eps_html = await hdtoday_fetch_html(
                        f"{base_url}/ajax/season/episodes/{s_id}", ttl=600
                    )
                    if eps_html:
                        ep_soup = BeautifulSoup(eps_html, "html.parser")
                        for ep_item in ep_soup.select(".eps-item"):
                            ep_id = ep_item.get("data-id")
                            ep_title = ep_item.get("title", "")
                            ep_num_match = re.search(
                                r"Eps?\s*(\d+)", ep_title, re.IGNORECASE
                            )
                            ep_num = (
                                int(ep_num_match.group(1))
                                if ep_num_match
                                else len(videos) + 1
                            )

                            videos.append(
                                {
                                    "id": f"hdtoday:series:{slug_id}:{s_num}:{ep_num}:{ep_id}",
                                    "title": f"S{s_num}E{ep_num}: {ep_title}",
                                    "season": s_num,
                                    "episode": ep_num,
                                    "released": release_info,
                                }
                            )

        meta = {
            "id": f"hdtoday:{m_type}:{slug_id}",
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
        logger.error(f"Error fetching HDToday meta for {id}: {e}")
        return {"meta": {}}


# ------------------------------------------------------------------
# Stream Resolver Helpers
# ------------------------------------------------------------------
async def resolve_vixsrc_stream(
    embed_url: str,
) -> Optional[Tuple[str, str, Dict[str, str]]]:
    """Resolve VixSrc embed URL to direct HLS master playlist URL and headers."""
    try:
        client = get_hdtoday_client()
        # Parse movie or tv tmdb info from vixsrc url:
        # e.g. https://vixsrc.to/movie/19995 or https://vixsrc.to/tv/33880/1/1
        m_match = re.search(
            r"vixsrc\.to/(movie|tv)/([0-9]+)(?:/([0-9]+)/([0-9]+))?", embed_url
        )
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

        api_res = await client.get(
            api_url, headers={"Referer": embed_url, "Origin": "https://vixsrc.to"}
        )
        if api_res.status_code != 200:
            return None

        api_data = api_res.json()
        src_path = api_data.get("src")
        if not src_path:
            return None

        embed_page_url = (
            f"https://vixsrc.to{src_path}"
            if src_path.startswith("/")
            else src_path
        )
        embed_html_res = await client.get(
            embed_page_url, headers={"Referer": embed_url}
        )
        if embed_html_res.status_code != 200:
            return None

        embed_html = embed_html_res.text
        token_m = re.search(
            r"['\"]token['\"]\s*:\s*['\"]([^'\"]+)['\"]", embed_html
        )
        expires_m = re.search(
            r"['\"]expires['\"]\s*:\s*['\"]([^'\"]+)['\"]", embed_html
        )
        url_m = re.search(
            r"url:\s*['\"](https://[^'\"]+)['\"]", embed_html
        )

        if token_m and expires_m and url_m:
            token = token_m.group(1)
            expires = expires_m.group(1)
            pl_base = url_m.group(1)
            m3u8_url = (
                f"{pl_base}?token={token}&expires={expires}&h=1&lang=en"
            )
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
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
@hdtoday_router.get("/hdtoday/stream/{type}/{id}.json")
@hdtoday_router.get("/stream/{type}/{id}.json")
async def hdtoday_stream_handler(request: Request, type: str, id: str):
    from config import Config

    base_url = getattr(Config, "HDTODAY_BASE_URL", HDTODAY_BASE_URL).rstrip("/")
    app_base_url = Config.ADDON_URL.rstrip("/") if getattr(Config, "ADDON_URL", None) and not Config.ADDON_URL.startswith("http://localhost") else str(request.base_url).rstrip("/")

    parts = id.split(":")
    # formats:
    # hdtoday:movie:avatar-7yeqHJL09WY
    # hdtoday:series:the-legend-of-korra-EOX7CgngyYz:1:1:w4Hy2vHaI9
    m_type = parts[1] if len(parts) > 1 else type
    slug_id = parts[2] if len(parts) > 2 else id
    ep_id = parts[5] if len(parts) >= 6 else (parts[3] if len(parts) == 4 else None)

    streams = []

    try:
        client = get_hdtoday_client()

        if m_type == "series" and ep_id:
            # TV episode servers
            servers_url = f"{base_url}/ajax/episode/servers/{ep_id}"
            servers_html = await hdtoday_fetch_html(servers_url, ttl=300)
            if not servers_html:
                return {"streams": []}

            soup = BeautifulSoup(servers_html, "html.parser")
            server_links = soup.select("a[data-id]")
        else:
            # Movie servers: get movie details page first to find data-id
            detail_url = f"{base_url}/movie/{slug_id}"
            detail_html = await hdtoday_fetch_html(detail_url, ttl=600)
            if not detail_html:
                return {"streams": []}

            d_soup = BeautifulSoup(detail_html, "html.parser")
            watch_div = d_soup.select_one(".detail_page-watch")
            movie_id = watch_div.get("data-id") if watch_div else ""
            if not movie_id:
                return {"streams": []}

            servers_url = f"{base_url}/ajax/episode/list/{movie_id}"
            servers_html = await hdtoday_fetch_html(servers_url, ttl=300)
            if not servers_html:
                return {"streams": []}

            soup = BeautifulSoup(servers_html, "html.parser")
            server_links = soup.select("a[data-id]")

        for link_el in server_links:
            server_id = link_el.get("data-id")
            server_title = link_el.get("title") or link_el.text.strip()
            if not server_id:
                continue

            # Fetch source url for server
            src_res = await client.get(
                f"{base_url}/ajax/episode/sources/{server_id}",
                headers={"Referer": f"{base_url}/"},
            )
            if src_res.status_code != 200:
                continue

            src_json = src_res.json()
            embed_link = src_json.get("link", "")
            if not embed_link:
                continue

            # Check if VixSrc / VixCloud
            if "vixsrc.to" in embed_link or "vixcloud" in embed_link:
                resolved = await resolve_vixsrc_stream(embed_link)
                if resolved:
                    m3u8_url, embed_ref, req_headers = resolved
                    proxy_endpoint = (
                        f"{app_base_url}/hdtoday/stream_proxy"
                        if not app_base_url.endswith("/hdtoday")
                        else f"{app_base_url}/stream_proxy"
                    )
                    proxy_stream_url = (
                        f"{proxy_endpoint}"
                        f"?url={urllib.parse.quote(m3u8_url, safe='')}"
                        f"&referer={urllib.parse.quote(embed_ref, safe='')}"
                    )

                    # 1. Native Stremio Internal Video Player (HLS Proxy - 100% playable with subtitles/multi-audio)
                    streams.append(
                        {
                            "name": f"HDToday [{server_title}]",
                            "title": (
                                f"▶ Phát Trực Tiếp trong Stremio [{server_title}]\n"
                                f"🎬 HDToday Full HD / HLS Stream\n"
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

                    # 2. Direct HLS Stream
                    streams.append(
                        {
                            "name": f"HDToday Direct [{server_title}]",
                            "title": f"⚡ Direct HLS Master Stream [{server_title}]",
                            "url": m3u8_url,
                            "behaviorHints": {
                                "notSupported": False,
                                "requestHeaders": req_headers,
                            },
                        }
                    )

            # Add Web Player fallback
            streams.append(
                {
                    "name": f"HDToday Web [{server_title}]",
                    "title": f"🌐 Mở Trình Duyệt Web [{server_title}]",
                    "externalUrl": embed_link,
                }
            )

        return {"streams": streams}

    except Exception as e:
        logger.error(f"Error fetching HDToday streams for {id}: {e}")
        return {"streams": []}


# ------------------------------------------------------------------
# HLS Stream Proxy
# ------------------------------------------------------------------
@hdtoday_router.get("/hdtoday/stream_proxy")
@hdtoday_router.get("/stream_proxy")
async def hdtoday_stream_proxy(
    request: Request, url: str, referer: Optional[str] = None
):
    """Proxy HLS master playlists, media playlists, and video chunks with correct Referer and CORS."""
    if not url:
        raise HTTPException(status_code=400, detail="Missing url parameter")

    client = get_hdtoday_client()
    ref_hdr = referer or "https://vixsrc.to/"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": ref_hdr,
        "Origin": "https://vixsrc.to",
    }

    # Pass Range header if client requested a byte range
    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header

    try:
        res = await client.get(url, headers=headers)

        content_type = res.headers.get("content-type", "")

        # If m3u8 playlist, rewrite URLs to route through proxy
        if (
            "mpegurl" in content_type.lower()
            or "application/x-mpegurl" in content_type.lower()
            or url.endswith(".m3u8")
            or "#EXTM3U" in res.text[:30]
        ):
            app_base_url = Config.ADDON_URL.rstrip("/") if getattr(Config, "ADDON_URL", None) and not Config.ADDON_URL.startswith("http://localhost") else str(request.base_url).rstrip("/")
            proxy_endpoint = (
                f"{app_base_url}/hdtoday/stream_proxy"
                if not app_base_url.endswith("/hdtoday")
                else f"{app_base_url}/stream_proxy"
            )
            lines = res.text.splitlines()
            rewritten_lines = []

            for line in lines:
                stripped = line.strip()
                if not stripped:
                    rewritten_lines.append(line)
                    continue

                if stripped.startswith("#"):
                    # Rewrite URI="..." in tags (e.g. #EXT-X-MEDIA:URI="..." or #EXT-X-KEY:URI="...")
                    if 'URI="' in stripped:

                        def rewrite_uri(match):
                            orig_uri = match.group(1)
                            abs_uri = urllib.parse.urljoin(url, orig_uri)
                            proxy_uri = (
                                f"{proxy_endpoint}"
                                f"?url={urllib.parse.quote(abs_uri, safe='')}"
                                f"&referer={urllib.parse.quote(ref_hdr, safe='')}"
                            )
                            return f'URI="{proxy_uri}"'

                        rewritten_line = re.sub(
                            r'URI="([^"]+)"', rewrite_uri, stripped
                        )
                        rewritten_lines.append(rewritten_line)
                    else:
                        rewritten_lines.append(line)
                else:
                    # Media playlist or chunk line
                    abs_chunk_url = urllib.parse.urljoin(url, stripped)
                    proxy_chunk_url = (
                        f"{proxy_endpoint}"
                        f"?url={urllib.parse.quote(abs_chunk_url, safe='')}"
                        f"&referer={urllib.parse.quote(ref_hdr, safe='')}"
                    )
                    rewritten_lines.append(proxy_chunk_url)

            body = "\n".join(rewritten_lines).encode("utf-8")
            resp_headers = {
                "Content-Type": "application/vnd.apple.mpegurl",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
                "Cache-Control": "no-cache",
            }
            return Response(content=body, headers=resp_headers)

        # For media chunks (.ts, .m4s, etc.), stream response directly
        resp_headers = {
            "Content-Type": content_type or "video/MP2T",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Accept-Ranges": "bytes",
        }
        if "content-length" in res.headers:
            resp_headers["Content-Length"] = res.headers["content-length"]
        if "content-range" in res.headers:
            resp_headers["Content-Range"] = res.headers["content-range"]

        return Response(
            content=res.content,
            status_code=res.status_code,
            headers=resp_headers,
        )

    except Exception as e:
        logger.error(f"Error in HDToday stream proxy for {url}: {e}")
        raise HTTPException(status_code=502, detail=f"Proxy error: {e}")
