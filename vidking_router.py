import asyncio
import base64
import json
import logging
import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from config import Config

logger = logging.getLogger(__name__)

vidking_router = APIRouter(prefix="", tags=["vidking"])

VIDKING_API_BASE = "https://api.speedracelight.com"
VIDKING_TMDB_BASE = "https://db.speedracelight.com/3"

# ------------------------------------------------------------------
# In-memory Caches
# ------------------------------------------------------------------
_vidking_cache: Dict[str, Tuple[Any, float]] = {}
_vidking_seeds: Dict[str, Tuple[str, float]] = {}
VIDKING_CACHE_TTL = 600  # 10 minutes

_vidking_client: Optional[httpx.AsyncClient] = None
_client_loop: Optional[asyncio.AbstractEventLoop] = None


def get_vidking_client() -> httpx.AsyncClient:
    global _vidking_client, _client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if (
        _vidking_client is None
        or _vidking_client.is_closed
        or _client_loop != current_loop
        or (current_loop and current_loop.is_closed())
    ):
        _client_loop = current_loop
        _vidking_client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=6.0),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=30, max_connections=60),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.vidking.net/",
                "Origin": "https://www.vidking.net",
            },
        )
    return _vidking_client


# ------------------------------------------------------------------
# Pure Python Decryption Engine for Vidking Stream Payloads
# ------------------------------------------------------------------
_HL = [
    1116352408, 1899447441, 3049323471, 3921009573,
    961987163, 1508970993, 2453635748, 2870763221,
    3624381080, 310598401, 607225278, 1426881987,
    1925078388, 2162078206, 2614888103, 3248222580
]
_F_INIT = [1732584193, 4023233417, 2562383102, 271733878]
_JS_CONST = 61
_SF_CONST = 8
_MS_CONST = 2654435769
_MAGIC_HEADER = [109, 118, 109, 49]  # b"mvm1"


def _u32(val: int) -> int:
    return val & 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    a = a & 0xFFFFFFFF
    b = b & 0xFFFFFFFF
    if a >= 0x80000000:
        a -= 0x100000000
    if b >= 0x80000000:
        b -= 0x100000000
    return (a * b) & 0xFFFFFFFF


def _bf(l_val: int) -> bool:
    return ((l_val * (l_val + 1)) & 1) == 0


def _if_cond(l_val: int) -> bool:
    return ((l_val * (l_val + 1)) & 1) == 1


def _ci(l_val: int) -> int:
    l_val = _u32(l_val)
    l_val ^= (l_val >> 16)
    l_val = _u32(_imul(l_val, 2246822507))
    l_val ^= (l_val >> 13)
    l_val = _u32(_imul(l_val, 3266489909))
    l_val ^= (l_val >> 16)
    return _u32(l_val)


def _ps(l_val: int, o_val: int) -> int:
    l_val = _u32(l_val)
    o_val &= 31
    if o_val == 0:
        return l_val
    return _u32((l_val << o_val) | (l_val >> (32 - o_val)))


def _af(l_str: str) -> int:
    o_val = _u32(_F_INIT[0])
    for e_idx, ch in enumerate(l_str):
        o_val = _ps(_u32(o_val ^ _imul(ord(ch), _HL[e_idx & 15])), 5)
    return _ci(o_val)


def _wf(l_str: str) -> List[int]:
    o_arr = list(range(256))
    e_val = 0
    str_len = len(l_str)
    for i in range(256):
        e_val = (e_val + o_arr[i] + ord(l_str[i % str_len])) & 255
        o_arr[i], o_arr[e_val] = o_arr[e_val], o_arr[i]
    return o_arr


def _vf(l_str: str) -> int:
    o_val = 2166136261
    for ch in l_str:
        o_val = _u32(_imul(o_val ^ ord(ch), 16777619))
    return _ci(o_val)


def _nf(l_val: int, o_val: int, e_val: int) -> int:
    return _u32((l_val ^ o_val) | (l_val & o_val & e_val))


class _CipherState:
    def __init__(self, s_table: Any, acc: int):
        self.s = s_table
        self.acc = acc


def _rf(l_seed: str, o_tmdb: int) -> _CipherState:
    if _if_cond(len(l_seed)):
        return _CipherState(_wf(l_seed), _af(l_seed))
    e_dict: Dict[int, int] = {}
    i_val = _ci(_vf(l_seed) ^ _ci(_u32(o_tmdb ^ _MS_CONST)))
    for r_idx in range(_SF_CONST):
        if _bf(r_idx):
            n_val = i_val % _JS_CONST
            i_val = _ps(_u32(i_val + _MS_CONST), 7 + (r_idx & 7))
            e_dict[n_val] = _u32(i_val ^ _ci(i_val))
            i_val = _ci(_u32(i_val + n_val))
        else:
            e_dict[r_idx] = _HL[r_idx & 15]
    return _CipherState(e_dict, _ci(i_val ^ 2779096485))


def _cf(state: _CipherState, o_step: int) -> int:
    e_tbl = state.s
    i_acc = state.acc
    r_idx = i_acc % _JS_CONST
    n_flag = 0 - (1 if r_idx in e_tbl else 0)
    u_val = _u32(e_tbl.get(r_idx, 0)) if isinstance(e_tbl, dict) else _u32(e_tbl[r_idx])
    d_val = _u32(_imul(_MS_CONST, o_step + 1))
    g_val = _nf(i_acc, _u32(u_val ^ d_val), n_flag)
    g_val = _u32(_ps(_u32(g_val + i_acc), r_idx & 31) ^ _ps(i_acc, (_imul(r_idx, 7) & 31)))
    i_acc = _ci(_u32(g_val + _MS_CONST))
    e_tbl[r_idx] = _u32(i_acc)
    state.acc = i_acc
    return _u32(i_acc)


def _xf(l_seed: str, o_tmdb: int, length: int) -> bytearray:
    state = _rf(l_seed, o_tmdb)
    r_bytes = bytearray(length)
    u_idx = 0
    n_step = 0
    while u_idx < length:
        d_word = _cf(state, n_step)
        n_step += 1
        r_bytes[u_idx] = d_word & 255
        u_idx += 1
        if u_idx < length:
            r_bytes[u_idx] = (d_word >> 8) & 255
            u_idx += 1
        if u_idx < length:
            r_bytes[u_idx] = (d_word >> 16) & 255
            u_idx += 1
        if u_idx < length:
            r_bytes[u_idx] = (d_word >> 24) & 255
            u_idx += 1
    return r_bytes


def _df(b64_cipher: str) -> bytearray:
    rem = len(b64_cipher) % 4
    if rem > 0:
        b64_cipher += "=" * (4 - rem)
    b64_cipher = b64_cipher.replace("-", "+").replace("_", "/")
    return bytearray(base64.b64decode(b64_cipher))


def decrypt_vidking_payload(ciphertext: str, seed: str, tmdb_id: int) -> str:
    """Decrypts encrypted Vidking response payload using pure Python."""
    data_bytes = _df(ciphertext)
    keystream = _xf(seed, int(tmdb_id), len(data_bytes))
    for n in range(len(data_bytes)):
        data_bytes[n] ^= keystream[n]
    for n in range(len(_MAGIC_HEADER)):
        if data_bytes[n] != _MAGIC_HEADER[n]:
            raise ValueError(f"Vidking decrypt failed: magic header mismatch")
    return data_bytes[len(_MAGIC_HEADER):].decode("utf-8")


# ------------------------------------------------------------------
# Speedracelight / Vidking API Helpers
# ------------------------------------------------------------------
async def get_vidking_seed(media_id: int) -> Optional[str]:
    """Retrieves session seed for given media ID from Speedracelight API."""
    now = time.time()
    cache_key = f"seed:{media_id}"
    if cache_key in _vidking_seeds:
        seed_val, expire = _vidking_seeds[cache_key]
        if now < expire:
            return seed_val

    client = get_vidking_client()
    try:
        res = await client.get(
            f"{VIDKING_API_BASE}/seed",
            params={"mediaId": str(media_id)},
            headers={"Cache-Control": "no-cache"},
            timeout=httpx.Timeout(6.0, connect=3.0)
        )
        if res.status_code == 200:
            data = res.json()
            seed = data.get("seed")
            ttl_s = (data.get("ttlMs", 30000) / 1000.0) - 3.0
            if seed:
                _vidking_seeds[cache_key] = (seed, now + max(5.0, ttl_s))
                return seed
    except Exception as e:
        logger.error(f"Error fetching Vidking seed for media {media_id}: {e}")
    return None


async def vidking_fetch_tmdb_json(endpoint: str, params: Optional[Dict[str, Any]] = None, ttl: int = VIDKING_CACHE_TTL) -> Optional[Dict[str, Any]]:
    """Fetches TMDB data from Vidking mirror with caching."""
    now = time.time()
    query_str = urllib.parse.urlencode(sorted((params or {}).items()))
    cache_key = f"tmdb:{endpoint}?{query_str}"
    if cache_key in _vidking_cache:
        data, exp = _vidking_cache[cache_key]
        if now < exp:
            return data

    client = get_vidking_client()
    for attempt in range(2):
        try:
            url = f"{VIDKING_TMDB_BASE}/{endpoint.lstrip('/')}"
            res = await client.get(url, params=params, timeout=httpx.Timeout(6.0, connect=3.0))
            if res.status_code == 200:
                data = res.json()
                _vidking_cache[cache_key] = (data, now + ttl)
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
            logger.error(f"Vidking TMDB fetch error for {endpoint}: {e}")
            return None
    return None


# ------------------------------------------------------------------
# Genres & Filter Definitions
# ------------------------------------------------------------------
GENRES_MAP = {
    "Action": 28,
    "Adventure": 12,
    "Animation": 16,
    "Comedy": 35,
    "Crime": 80,
    "Documentary": 99,
    "Drama": 18,
    "Family": 10751,
    "Fantasy": 14,
    "History": 36,
    "Horror": 27,
    "Music": 10402,
    "Mystery": 9648,
    "Romance": 10749,
    "Sci-Fi": 878,
    "Thriller": 53,
    "War": 10752,
    "Western": 37,
}
ALL_GENRE_OPTIONS = list(GENRES_MAP.keys())


# ------------------------------------------------------------------
# Manifest
# ------------------------------------------------------------------
def get_vidking_manifest() -> Dict[str, Any]:
    from config import Config

    show_on_board = getattr(Config, "ENABLE_BOARD_VIDKING", True)
    main_req = not show_on_board

    return {
        "id": "com.stremio.vidking.addon",
        "version": "1.0.0",
        "name": "Vidking Player - Movies & TV Series HD",
        "description": "Stream High Quality Movies & TV Shows from Vidking Player (4K / 1080p HLS & MP4 Streams)",
        "logo": "https://www.vidking.net/assets/icon/apple-icon-180x180.png",
        "resources": [
            "catalog",
            {
                "name": "meta",
                "types": ["movie", "series"],
                "idPrefixes": ["vidking:", "tmdb:", "tt"],
            },
            {
                "name": "stream",
                "types": ["movie", "series"],
                "idPrefixes": ["vidking:", "tmdb:", "tt"],
            },
        ] + ([
            {
                "name": "subtitles",
                "types": ["movie", "series"],
                "idPrefixes": ["vidking:", "tmdb:", "tt"],
            }
        ] if getattr(Config, "ENABLE_SUBTITLES", True) else []),
        "types": ["movie", "series"],
        "catalogs": [
            {
                "type": "movie",
                "id": "vidking_popular_movie",
                "name": "Vidking - Popular Movies",
                "extra": [
                    {
                        "name": "genre",
                        "options": ["Tất cả"] + ALL_GENRE_OPTIONS,
                        "isRequired": main_req,
                    },
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "type": "movie",
                "id": "vidking_top_rated_movie",
                "name": "Vidking - Top Rated Movies",
                "extra": [
                    {
                        "name": "genre",
                        "options": ["Tất cả"] + ALL_GENRE_OPTIONS,
                        "isRequired": main_req,
                    },
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "type": "series",
                "id": "vidking_trending_series",
                "name": "Vidking - Trending TV Shows",
                "extra": [
                    {
                        "name": "genre",
                        "options": ["Tất cả"] + ALL_GENRE_OPTIONS,
                        "isRequired": main_req,
                    },
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "type": "series",
                "id": "vidking_popular_series",
                "name": "Vidking - Popular TV Shows",
                "extra": [
                    {
                        "name": "genre",
                        "options": ["Tất cả"] + ALL_GENRE_OPTIONS,
                        "isRequired": main_req,
                    },
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
        ],
        "behaviorHints": {
            "configurable": False,
            "configurationRequired": False,
        },
    }


@vidking_router.get("/vidking/manifest.json")
@vidking_router.get("/manifest.json")
async def vidking_manifest_endpoint():
    from config import Config
    if not getattr(Config, "ENABLE_SOURCE_VIDKING", True):
        raise HTTPException(status_code=404, detail="Vidking source is disabled.")
    return get_vidking_manifest()


# ------------------------------------------------------------------
# Catalog Handler
# ------------------------------------------------------------------
def _format_tmdb_meta_item(item: Dict[str, Any], item_type: str, imdb_id: Optional[str] = None) -> Dict[str, Any]:
    tmdb_id = item.get("id")
    title = item.get("title") or item.get("name") or "Unknown Title"
    rel_date = item.get("release_date") or item.get("first_air_date") or ""
    year = rel_date[:4] if len(rel_date) >= 4 else ""
    poster_path = item.get("poster_path")
    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
    backdrop_path = item.get("backdrop_path")
    backdrop_url = f"https://image.tmdb.org/t/p/original{backdrop_path}" if backdrop_path else poster_url
    overview = item.get("overview") or ""
    vote_avg = item.get("vote_average", 0.0)

    desc_lines = []
    if year:
        desc_lines.append(f"📅 Năm: {year}")
    if vote_avg:
        desc_lines.append(f"⭐ IMDb/TMDB: {vote_avg:.1f}/10")
    if overview:
        desc_lines.append(f"\n{overview}")

    stremio_id = imdb_id if (imdb_id and imdb_id.startswith("tt")) else f"vidking:{item_type}:{tmdb_id}"
    return {
        "id": stremio_id,
        "type": item_type,
        "name": title,
        "poster": poster_url,
        "background": backdrop_url,
        "description": "\n".join(desc_lines),
        "releaseInfo": year,
        "imdbRating": str(round(vote_avg, 1)) if vote_avg else None,
    }


async def _enrich_items_with_imdb(results: List[Dict[str, Any]], media_endpoint_type: str) -> List[Dict[str, Any]]:
    """Enriches TMDB catalog items with their IMDb ID for full Stremio subtitle addon compatibility."""
    tasks = []
    for item in results:
        tmdb_id = item.get("id")
        if not tmdb_id:
            tasks.append(asyncio.sleep(0))
            continue
        cache_key = f"imdb_id:{media_endpoint_type}:{tmdb_id}"
        if cache_key in _vidking_cache and time.time() < _vidking_cache[cache_key][1]:
            tasks.append(asyncio.sleep(0))
        else:
            tasks.append(vidking_fetch_tmdb_json(f"/{media_endpoint_type}/{tmdb_id}", params={"append_to_response": "external_ids"}, ttl=86400))

    meta_results = await asyncio.gather(*tasks, return_exceptions=True)

    formatted = []
    for item, meta_res in zip(results, meta_results):
        tmdb_id = item.get("id")
        imdb_id = None
        cache_key = f"imdb_id:{media_endpoint_type}:{tmdb_id}"
        if cache_key in _vidking_cache and time.time() < _vidking_cache[cache_key][1]:
            imdb_id = _vidking_cache[cache_key][0]
        elif isinstance(meta_res, dict):
            imdb_id = meta_res.get("external_ids", {}).get("imdb_id")
            if imdb_id:
                _vidking_cache[cache_key] = (imdb_id, time.time() + 86400)
        formatted.append(_format_tmdb_meta_item(item, "movie" if media_endpoint_type == "movie" else "series", imdb_id))

    return formatted


@vidking_router.get("/vidking/catalog/{type}/{id}.json")
@vidking_router.get("/vidking/catalog/{type}/{id}/{extra:path}")
@vidking_router.get("/catalog/{type}/{id}.json")
@vidking_router.get("/catalog/{type}/{id}/{extra:path}")
async def vidking_catalog_handler(
    type: str,
    id: str,
    extra: Optional[str] = None,
    genre: Optional[str] = None,
    search: Optional[str] = None,
    skip: Optional[int] = None,
):
    from config import Config
    if not getattr(Config, "ENABLE_SOURCE_VIDKING", True):
        return {"metas": []}

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

    page = (skip_val // 20) + 1
    media_endpoint_type = "movie" if type == "movie" else "tv"

    # Search flow
    if search_val:
        endpoint = f"/search/{media_endpoint_type}"
        params = {"query": search_val, "page": page}
        data = await vidking_fetch_tmdb_json(endpoint, params=params, ttl=300)
        results = data.get("results", []) if data else []
        metas = await _enrich_items_with_imdb(results, media_endpoint_type)
        return {"metas": metas}

    # Genre discovery flow
    if genre_val and genre_val not in ["Tất cả", "All"]:
        genre_id = GENRES_MAP.get(genre_val)
        if genre_id:
            endpoint = f"/discover/{media_endpoint_type}"
            params = {"with_genres": str(genre_id), "page": page, "sort_by": "popularity.desc"}
            data = await vidking_fetch_tmdb_json(endpoint, params=params, ttl=600)
            results = data.get("results", []) if data else []
            metas = await _enrich_items_with_imdb(results, media_endpoint_type)
            return {"metas": metas}

    # Standard catalog endpoints
    if id == "vidking_top_rated_movie":
        endpoint = "/movie/top_rated"
    elif id == "vidking_trending_series":
        endpoint = "/trending/tv/week"
    elif id == "vidking_popular_series":
        endpoint = "/tv/popular"
    else:
        endpoint = "/movie/popular"

    params = {"page": page}
    data = await vidking_fetch_tmdb_json(endpoint, params=params, ttl=600)
    results = data.get("results", []) if data else []
    metas = await _enrich_items_with_imdb(results, media_endpoint_type)
    return {"metas": metas}


# ------------------------------------------------------------------
# Meta Handler
# ------------------------------------------------------------------
@vidking_router.get("/vidking/meta/{type}/{id}.json")
@vidking_router.get("/meta/{type}/{id}.json")
async def vidking_meta_handler(type: str, id: str):
    from config import Config
    if not getattr(Config, "ENABLE_SOURCE_VIDKING", True):
        return {"meta": {}}

    # Parse ID
    tmdb_id: Optional[str] = None
    media_type = "movie" if type == "movie" else "tv"
    orig_imdb_id: Optional[str] = None

    if id.startswith("vidking:"):
        parts = id.split(":")
        if len(parts) >= 3:
            media_type = "tv" if parts[1] == "series" else "movie"
            tmdb_id = parts[2]
        elif len(parts) == 2:
            tmdb_id = parts[1]
    elif id.startswith("tmdb:"):
        parts = id.split(":")
        if len(parts) >= 2:
            tmdb_id = parts[1]
    elif id.startswith("tt"):
        orig_imdb_id = id
        find_data = await vidking_fetch_tmdb_json(f"/find/{id}", params={"external_source": "imdb_id"})
        if find_data:
            if type == "movie" and find_data.get("movie_results"):
                tmdb_id = str(find_data["movie_results"][0]["id"])
            elif find_data.get("tv_results"):
                tmdb_id = str(find_data["tv_results"][0]["id"])
                media_type = "tv"
            elif find_data.get("movie_results"):
                tmdb_id = str(find_data["movie_results"][0]["id"])
                media_type = "movie"
    else:
        tmdb_id = id

    if not tmdb_id:
        return {"meta": {}}

    detail_data = await vidking_fetch_tmdb_json(f"/{media_type}/{tmdb_id}", params={"append_to_response": "credits,external_ids"})
    if not detail_data:
        return {"meta": {}}

    title = detail_data.get("title") or detail_data.get("name") or "Unknown"
    rel_date = detail_data.get("release_date") or detail_data.get("first_air_date") or ""
    year = rel_date[:4] if len(rel_date) >= 4 else ""
    poster_path = detail_data.get("poster_path")
    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
    backdrop_path = detail_data.get("backdrop_path")
    backdrop_url = f"https://image.tmdb.org/t/p/original{backdrop_path}" if backdrop_path else poster_url
    overview = detail_data.get("overview") or ""
    vote_avg = detail_data.get("vote_average", 0.0)
    genres = [g.get("name") for g in detail_data.get("genres", []) if g.get("name")]
    cast = [c.get("name") for c in detail_data.get("credits", {}).get("cast", [])[:8] if c.get("name")]

    imdb_id = orig_imdb_id or detail_data.get("external_ids", {}).get("imdb_id")
    stremio_id = imdb_id if (imdb_id and imdb_id.startswith("tt")) else f"vidking:{type}:{tmdb_id}"

    meta: Dict[str, Any] = {
        "id": stremio_id,
        "type": type,
        "name": title,
        "poster": poster_url,
        "background": backdrop_url,
        "description": overview,
        "releaseInfo": year,
        "genres": genres,
        "cast": cast,
        "imdbRating": str(round(vote_avg, 1)) if vote_avg else None,
    }

    # Process TV Series Seasons & Episodes
    if type == "series" or media_type == "tv":
        videos = []
        seasons = detail_data.get("seasons", [])
        for season in seasons:
            s_num = season.get("season_number")
            if s_num is None or s_num == 0:
                continue
            ep_count = season.get("episode_count", 0)
            # Fetch season details if available
            s_data = await vidking_fetch_tmdb_json(f"/tv/{tmdb_id}/season/{s_num}", ttl=1800)
            episodes = s_data.get("episodes", []) if s_data else []
            if episodes:
                for ep in episodes:
                    ep_num = ep.get("episode_number")
                    ep_title = ep.get("name") or f"Episode {ep_num}"
                    ep_still = ep.get("still_path")
                    thumb = f"https://image.tmdb.org/t/p/w500{ep_still}" if ep_still else poster_url
                    ep_air = ep.get("air_date") or ""
                    ep_overview = ep.get("overview") or ""
                    ep_id = f"{imdb_id}:{s_num}:{ep_num}" if (imdb_id and imdb_id.startswith("tt")) else f"vidking:series:{tmdb_id}:{s_num}:{ep_num}"
                    videos.append({
                        "id": ep_id,
                        "title": ep_title,
                        "season": s_num,
                        "episode": ep_num,
                        "released": ep_air,
                        "overview": ep_overview,
                        "thumbnail": thumb,
                    })
            else:
                for ep_num in range(1, ep_count + 1):
                    ep_id = f"{imdb_id}:{s_num}:{ep_num}" if (imdb_id and imdb_id.startswith("tt")) else f"vidking:series:{tmdb_id}:{s_num}:{ep_num}"
                    videos.append({
                        "id": ep_id,
                        "title": f"Tập {ep_num}",
                        "season": s_num,
                        "episode": ep_num,
                    })
        meta["videos"] = videos

    return {"meta": meta}

    return {"meta": meta}


# ------------------------------------------------------------------
# Stream Resolution & Decryption Engine
# ------------------------------------------------------------------
VIDKING_SERVERS = [
    {"name": "Yoru (HLS Fast)", "endpoint": "cdn/sources-with-title", "priority": 10},
    {"name": "Cypher (Direct MP4)", "endpoint": "downloader2/sources-with-title", "priority": 9},
    {"name": "Neon", "endpoint": "vsrc/sources-with-title", "priority": 8},
    {"name": "Vyse (HD)", "endpoint": "hdmovie/sources-with-title", "priority": 7},
    {"name": "Breach", "endpoint": "m4uhd/sources-with-title", "priority": 6},
    {"name": "Raze", "endpoint": "superflix/sources-with-title", "priority": 5},
    {"name": "Omen", "endpoint": "lamovie/sources-with-title", "priority": 4},
]


async def fetch_and_decrypt_server(
    server_cfg: Dict[str, Any],
    tmdb_id: int,
    media_type: str,
    title: str,
    year: str,
    imdb_id: str,
    season: int = 1,
    episode: int = 1,
    seed: str = "",
    base_url: str = "",
) -> List[Dict[str, Any]]:
    """Requests and decrypts streams from a single Vidking server."""
    client = get_vidking_client()
    endpoint = server_cfg["endpoint"]
    server_name = server_cfg["name"]

    params = {
        "title": title,
        "mediaType": "tv" if media_type == "tv" or media_type == "series" else "movie",
        "year": str(year),
        "episodeId": str(episode),
        "seasonId": str(season),
        "tmdbId": str(tmdb_id),
        "imdbId": imdb_id or "",
        "enc": "2",
        "seed": seed,
        "_t": str(int(time.time() * 1000)),
    }

    try:
        url = f"{VIDKING_API_BASE}/{endpoint}"
        res = await client.get(url, params=params, timeout=httpx.Timeout(6.0, connect=3.0))
        if res.status_code == 200:
            ciphertext = res.text.strip()
            decrypted_str = decrypt_vidking_payload(ciphertext, seed, tmdb_id)
            data = json.loads(decrypted_str)
            sources = data.get("sources", [])
            subtitles = data.get("subtitles", [])

            extracted = []
            for src in sources:
                if not isinstance(src, dict):
                    continue
                s_url = src.get("url")
                quality = src.get("quality") or "HD"
                if not s_url:
                    continue

                # Format quality badge
                q_badge = "4K 2160p" if "2160" in str(quality) else ("1080p FHD" if "1080" in str(quality) else ("720p HD" if "720" in str(quality) else str(quality)))
                is_hls = ".m3u8" in s_url.lower() or src.get("type") == "hls"
                stream_type_label = "⚡ HLS" if is_hls else "🚀 MP4"

                clean_fn_title = re.sub(r'[\\/*?:"<>|]', "", title).strip()
                if media_type in ["tv", "series"]:
                    fn_name = f"{clean_fn_title} S{season:02d}E{episode:02d}.mp4"
                else:
                    fn_name = f"{clean_fn_title} ({year}).mp4" if year else f"{clean_fn_title}.mp4"

                # Route through stream proxy to inject Referer header and bypass 403 Forbidden
                if base_url:
                    proxy_path = f"{base_url}/vidking/stream_proxy" if not base_url.endswith("/vidking") else f"{base_url}/stream_proxy"
                    final_url = f"{proxy_path}?url={urllib.parse.quote(s_url, safe='')}&referer={urllib.parse.quote('https://www.vidking.net/', safe='')}"
                else:
                    final_url = s_url

                stremio_stream = {
                    "name": f"Vidking\n{q_badge}",
                    "title": f"🎬 {title} {f'S{season:02d}E{episode:02d}' if (media_type in ['tv', 'series']) else ''}\n📡 Server: {server_name} | {stream_type_label}\n✨ Quality: {q_badge}",
                    "url": final_url,
                    "behaviorHints": {
                        "notWebReady": False,
                        "bingeGroup": f"vidking-{tmdb_id}",
                        "filename": fn_name,
                    }
                }

                # Attach subtitles if present and enabled
                if getattr(Config, "ENABLE_SUBTITLES", True) and subtitles and isinstance(subtitles, list):
                    st_list = []
                    for st in subtitles:
                        if isinstance(st, dict) and st.get("url"):
                            st_list.append({
                                "id": st.get("lang") or "sub",
                                "url": st.get("url"),
                                "lang": st.get("language") or st.get("lang") or "eng",
                            })
                    if st_list:
                        stremio_stream["subtitles"] = st_list

                extracted.append(stremio_stream)

            return extracted
    except Exception as e:
        logger.debug(f"Vidking server {server_name} error for {tmdb_id}: {e}")
    return []


@vidking_router.get("/vidking/stream/{type}/{id}.json")
@vidking_router.get("/stream/{type}/{id}.json")
async def vidking_stream_handler(type: str, id: str, request: Request = None):
    from config import Config
    if not getattr(Config, "ENABLE_SOURCE_VIDKING", True):
        return {"streams": []}

    base_url = Config.ADDON_URL.rstrip("/") if getattr(Config, "ADDON_URL", None) else (str(request.base_url).rstrip("/") if request else "http://127.0.0.1:7860")

    # Parse media details
    tmdb_id: Optional[int] = None
    media_type = "movie" if type == "movie" else "tv"
    season = 1
    episode = 1
    imdb_id = ""

    if id.startswith("vidking:"):
        parts = id.split(":")
        if len(parts) >= 5:
            media_type = "tv" if parts[1] == "series" else "movie"
            tmdb_id = int(parts[2])
            season = int(parts[3])
            episode = int(parts[4])
        elif len(parts) >= 3:
            media_type = "tv" if parts[1] == "series" else "movie"
            tmdb_id = int(parts[2])
        elif len(parts) == 2:
            tmdb_id = int(parts[1])
    elif id.startswith("tmdb:"):
        parts = id.split(":")
        if len(parts) >= 4:
            tmdb_id = int(parts[1])
            season = int(parts[2])
            episode = int(parts[3])
            media_type = "tv"
        elif len(parts) >= 2:
            tmdb_id = int(parts[1])
    elif id.startswith("tt"):
        # IMDb ID: format tt1234567 or tt1234567:1:1
        parts = id.split(":")
        imdb_code = parts[0]
        if len(parts) >= 3:
            season = int(parts[1])
            episode = int(parts[2])
            media_type = "tv"
        imdb_id = imdb_code
        find_data = await vidking_fetch_tmdb_json(f"/find/{imdb_code}", params={"external_source": "imdb_id"})
        if find_data:
            if media_type == "tv" and find_data.get("tv_results"):
                tmdb_id = int(find_data["tv_results"][0]["id"])
            elif find_data.get("movie_results"):
                tmdb_id = int(find_data["movie_results"][0]["id"])
            elif find_data.get("tv_results"):
                tmdb_id = int(find_data["tv_results"][0]["id"])
                media_type = "tv"

    if not tmdb_id:
        return {"streams": []}

    # Fetch TMDB metadata for title, year, imdb_id
    detail_data = await vidking_fetch_tmdb_json(f"/{media_type}/{tmdb_id}", params={"append_to_response": "external_ids"})
    if not detail_data:
        return {"streams": []}

    title = detail_data.get("title") or detail_data.get("name") or "Movie"
    rel_date = detail_data.get("release_date") or detail_data.get("first_air_date") or ""
    year = rel_date[:4] if len(rel_date) >= 4 else ""
    if not imdb_id:
        imdb_id = detail_data.get("external_ids", {}).get("imdb_id", "")

    # Get dynamic session seed
    seed = await get_vidking_seed(tmdb_id)
    if not seed:
        return {"streams": []}

    # Fetch stream sources in parallel across top servers
    tasks = [
        fetch_and_decrypt_server(
            server_cfg=srv,
            tmdb_id=tmdb_id,
            media_type=media_type,
            title=title,
            year=year,
            imdb_id=imdb_id,
            season=season,
            episode=episode,
            seed=seed,
            base_url=base_url,
        )
        for srv in VIDKING_SERVERS
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    all_streams: List[Dict[str, Any]] = []
    for res_list in results:
        if isinstance(res_list, list):
            all_streams.extend(res_list)

    # Sort streams: 4K (2160p) > 1080p > 720p > 480p
    def quality_score(item: Dict[str, Any]) -> int:
        title_str = item.get("title", "") + item.get("name", "")
        if "2160" in title_str or "4K" in title_str:
            return 400
        if "1080" in title_str:
            return 300
        if "720" in title_str:
            return 200
        if "480" in title_str:
            return 100
        return 50

    all_streams.sort(key=quality_score, reverse=True)
    return {"streams": all_streams}


# ------------------------------------------------------------------
# Stream Proxy Handler (Referer & CORS bypass)
# ------------------------------------------------------------------
@vidking_router.get("/vidking/stream_proxy")
@vidking_router.get("/stream_proxy")
async def vidking_stream_proxy(
    request: Request,
    url: str,
    referer: Optional[str] = "https://www.vidking.net/",
):
    """Proxies HLS playlists (.m3u8) and video segments (.ts, .m4s, .mp4) with proper Referer & CORS."""
    client = get_vidking_client()
    ref_hdr = referer or "https://www.vidking.net/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": ref_hdr,
        "Origin": "https://www.vidking.net",
    }

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
            from config import Config
            app_base_url = Config.ADDON_URL.rstrip("/") if getattr(Config, "ADDON_URL", None) else str(request.base_url).rstrip("/")
            proxy_endpoint = (
                f"{app_base_url}/vidking/stream_proxy"
                if not app_base_url.endswith("/vidking")
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

                        rewritten_line = re.sub(r'URI="([^"]+)"', rewrite_uri, stripped)
                        rewritten_lines.append(rewritten_line)
                    else:
                        rewritten_lines.append(line)
                else:
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

        # For media chunks (.ts, .m4s, .mp4 etc.)
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
        logger.error(f"Error in Vidking stream proxy for {url}: {e}")
        raise HTTPException(status_code=502, detail=f"Proxy error: {e}")


# ------------------------------------------------------------------
# Subtitles Handler (OpenSubtitles Bridge & Auto Vietsub)
# ------------------------------------------------------------------
OPENSUBTITLES_BASE = "https://opensubtitles-v3.strem.io/subtitles/"


async def resolve_imdb_id_for_vidking(media_type: str, id_str: str) -> Tuple[Optional[str], int, int]:
    """Resolves any vidking/tmdb/tt id to standard IMDb id format (e.g. tt0137523 or tt0903747:1:1)."""
    tmdb_id: Optional[str] = None
    season = 1
    episode = 1
    m_type = "movie" if media_type == "movie" else "tv"

    if id_str.startswith("tt"):
        parts = id_str.split(":")
        if len(parts) >= 3:
            return id_str, int(parts[1]), int(parts[2])
        return id_str, 1, 1

    if id_str.startswith("vidking:"):
        parts = id_str.split(":")
        if len(parts) >= 5:
            m_type = "tv" if parts[1] == "series" else "movie"
            tmdb_id = parts[2]
            season = int(parts[3])
            episode = int(parts[4])
        elif len(parts) >= 3:
            m_type = "tv" if parts[1] == "series" else "movie"
            tmdb_id = parts[2]
        elif len(parts) == 2:
            tmdb_id = parts[1]
    elif id_str.startswith("tmdb:"):
        parts = id_str.split(":")
        if len(parts) >= 4:
            tmdb_id = parts[1]
            season = int(parts[2])
            episode = int(parts[3])
            m_type = "tv"
        elif len(parts) >= 2:
            tmdb_id = parts[1]
    else:
        tmdb_id = id_str

    if not tmdb_id:
        return None, season, episode

    meta = await vidking_fetch_tmdb_json(f"/{m_type}/{tmdb_id}", params={"append_to_response": "external_ids"})
    if meta:
        raw_imdb = meta.get("external_ids", {}).get("imdb_id", "")
        if raw_imdb:
            if m_type == "tv" or media_type == "series":
                return f"{raw_imdb}:{season}:{episode}", season, episode
            return raw_imdb, season, episode

    return None, season, episode


async def fetch_opensubtitles(imdb_target: str, media_type: str, extra: str = "") -> List[Dict[str, Any]]:
    client = get_vidking_client()
    stremio_type = "series" if media_type in ["series", "tv"] or ":" in imdb_target else "movie"
    url = f"{OPENSUBTITLES_BASE}{stremio_type}/{urllib.parse.quote(imdb_target)}.json"
    if extra:
        extra_clean = extra.rstrip(".json") if extra.endswith(".json") else extra
        url = f"{OPENSUBTITLES_BASE}{stremio_type}/{urllib.parse.quote(imdb_target)}/{extra_clean}.json"

    try:
        res = await client.get(url, timeout=httpx.Timeout(6.0, connect=3.0))
        if res.status_code == 200:
            data = res.json()
            return data.get("subtitles", [])
    except Exception as e:
        logger.debug(f"OpenSubtitles fetch error for {imdb_target}: {e}")
    return []


@vidking_router.get("/vidking/subtitles/{type}/{id}.json")
@vidking_router.get("/vidking/subtitles/{type}/{id}/{extra:path}")
@vidking_router.get("/subtitles/{type}/{id}.json")
@vidking_router.get("/subtitles/{type}/{id}/{extra:path}")
async def vidking_subtitles_handler(request: Request, type: str, id: str, extra: Optional[str] = None):
    from config import Config
    if not getattr(Config, "ENABLE_SOURCE_VIDKING", True) or not getattr(Config, "ENABLE_SUBTITLES", True):
        return {"subtitles": []}

    clean_id = id.replace(":", "_").replace("/", "_")
    base_url = Config.ADDON_URL.rstrip("/") if getattr(Config, "ADDON_URL", None) else str(request.base_url).rstrip("/")
    subtitles_list: List[Dict[str, Any]] = []

    # 1. Resolve IMDb ID for OpenSubtitles
    imdb_id, season, episode = await resolve_imdb_id_for_vidking(type, id)

    # 2. Add AI Vietnamese subtitle tracks if AUTO_VIET_SUB enabled
    if getattr(Config, "AUTO_VIET_SUB", True):
        target_id_for_vtt = imdb_id if imdb_id else id
        clean_vtt_id = target_id_for_vtt.replace(":", "_").replace("/", "_")
        fast_url = f"{base_url}/subtitles/vtt/{clean_vtt_id}.vtt?type={type}&track=fast"
        quality_url = f"{base_url}/subtitles/vtt/{clean_vtt_id}.vtt?type={type}&track=quality"
        subtitles_list.append({
            "id": f"vi_fast_{clean_id}",
            "url": fast_url,
            "lang": "vie",
            "name": "🇻🇳 Tiếng Việt - Nhanh (Lingva, toàn bộ phim)",
        })
        subtitles_list.append({
            "id": f"vi_quality_{clean_id}",
            "url": quality_url,
            "lang": "vie",
            "name": "🇻🇳 Tiếng Việt - AI chất lượng cao (Gemini, dịch ngầm)",
        })

    # 3. Query OpenSubtitles if IMDb ID resolved
    if imdb_id:
        os_subs = await fetch_opensubtitles(imdb_id, type, extra or "")
        subtitles_list.extend(os_subs)

    return JSONResponse(content={"subtitles": subtitles_list})

