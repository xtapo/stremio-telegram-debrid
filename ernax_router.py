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

ernax_router = APIRouter(prefix="", tags=["ernax"])

ERNAX_API_BASE = "https://api.speedracelight.com"
ERNAX_TMDB_BASE = "https://db.speedracelight.com/3"

# ------------------------------------------------------------------
# In-memory Caches
# ------------------------------------------------------------------
_ernax_cache: Dict[str, Tuple[Any, float]] = {}
_ernax_seeds: Dict[str, Tuple[str, float]] = {}
ERNAX_CACHE_TTL = 600  # 10 minutes

_ernax_client: Optional[httpx.AsyncClient] = None
_client_loop: Optional[asyncio.AbstractEventLoop] = None


def get_ernax_client() -> httpx.AsyncClient:
    global _ernax_client, _client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if (
        _ernax_client is None
        or _ernax_client.is_closed
        or _client_loop != current_loop
        or (current_loop and current_loop.is_closed())
    ):
        _client_loop = current_loop
        _ernax_client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=6.0),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=30, max_connections=60),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "https://ernax.pro/",
                "Origin": "https://ernax.pro",
            },
        )
    return _ernax_client


# ------------------------------------------------------------------
# Pure Python Decryption Engine for Ernax Stream Payloads
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


def decrypt_ernax_payload(ciphertext: str, seed: str, tmdb_id: int) -> str:
    """Decrypts encrypted Ernax response payload using pure Python."""
    data_bytes = _df(ciphertext)
    keystream = _xf(seed, int(tmdb_id), len(data_bytes))
    for n in range(len(data_bytes)):
        data_bytes[n] ^= keystream[n]
    for n in range(len(_MAGIC_HEADER)):
        if data_bytes[n] != _MAGIC_HEADER[n]:
            raise ValueError("Ernax decrypt failed: magic header mismatch")
    return data_bytes[len(_MAGIC_HEADER):].decode("utf-8")


# ------------------------------------------------------------------
# Speedracelight / Ernax API Helpers
# ------------------------------------------------------------------
async def get_ernax_seed(media_id: int) -> Optional[str]:
    """Retrieves session seed for given media ID from Speedracelight API."""
    now = time.time()
    cache_key = f"seed:{media_id}"
    if cache_key in _ernax_seeds:
        seed_val, expire = _ernax_seeds[cache_key]
        if now < expire:
            return seed_val

    client = get_ernax_client()
    try:
        res = await client.get(
            f"{ERNAX_API_BASE}/seed",
            params={"mediaId": str(media_id)},
            headers={"Cache-Control": "no-cache"},
            timeout=httpx.Timeout(6.0, connect=3.0),
        )
        if res.status_code == 200:
            data = res.json()
            seed = data.get("seed")
            if seed:
                _ernax_seeds[cache_key] = (seed, now + 25.0)
                return seed
    except Exception as e:
        logger.warning(f"[Ernax] Failed to get seed for mediaId={media_id}: {e}")
    return None


async def fetch_ernax_stream_sources(
    tmdb_id: int,
    media_type: str = "movie",
    title: str = "",
    year: str = "",
    imdb_id: str = "",
    season: int = 1,
    episode: int = 1,
    seed: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fetches and decrypts stream sources from Ernax CDN."""
    now = time.time()
    cache_key = f"stream:{media_type}:{tmdb_id}:{season}:{episode}"
    if cache_key in _ernax_cache:
        cached_data, expire = _ernax_cache[cache_key]
        if now < expire:
            return cached_data

    if not seed:
        seed = await get_ernax_seed(tmdb_id)
    if not seed:
        return None

    client = get_ernax_client()
    params = {
        "title": title,
        "mediaType": "movie" if media_type == "movie" else "tv",
        "year": str(year) if year else "",
        "episodeId": str(episode),
        "seasonId": str(season),
        "tmdbId": str(tmdb_id),
        "imdbId": imdb_id or "",
        "enc": "2",
        "seed": seed,
    }

    try:
        res = await client.get(
            f"{ERNAX_API_BASE}/cdn/sources-with-title",
            params=params,
            headers={
                "Referer": "https://ernax.pro/",
                "Origin": "https://ernax.pro",
            },
            timeout=httpx.Timeout(10.0, connect=4.0),
        )
        if res.status_code == 200 and res.text:
            raw_text = res.text.strip()
            decrypted_str = decrypt_ernax_payload(raw_text, seed, tmdb_id)
            stream_data = json.loads(decrypted_str)
            if isinstance(stream_data, dict):
                _ernax_cache[cache_key] = (stream_data, now + ERNAX_CACHE_TTL)
                return stream_data
    except Exception as e:
        logger.warning(f"[Ernax] Failed to fetch stream sources for tmdbId={tmdb_id}: {e}")
    return None


# ------------------------------------------------------------------
# TMDB Mirror API Handlers
# ------------------------------------------------------------------
async def ernax_fetch_tmdb_json(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Fetches TMDB metadata from speedracelight mirror or official endpoints with caching."""
    now = time.time()
    param_str = urllib.parse.urlencode(sorted((params or {}).items()))
    cache_key = f"tmdb:{endpoint}:{param_str}"
    if cache_key in _ernax_cache:
        cached_data, expire = _ernax_cache[cache_key]
        if now < expire:
            return cached_data

    client = get_ernax_client()
    req_params = dict(params or {})

    # Try speedracelight mirror
    try:
        url = f"{ERNAX_TMDB_BASE}{endpoint}"
        res = await client.get(url, params=req_params, timeout=httpx.Timeout(8.0, connect=3.0))
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict):
                _ernax_cache[cache_key] = (data, now + ERNAX_CACHE_TTL)
                return data
    except Exception as e:
        logger.debug(f"[Ernax] TMDB mirror request failed for {endpoint}: {e}")

    # Fallback to Cinemeta if TMDB mirror is unreachable
    try:
        if endpoint.startswith("/find/tt"):
            imdb_id = endpoint.replace("/find/", "").split("?")[0]
            c_url = f"https://v3-cinemeta.strem.io/meta/movie/{imdb_id}.json"
            res = await client.get(c_url, timeout=httpx.Timeout(6.0, connect=3.0))
            if res.status_code == 200:
                meta = res.json().get("meta", {})
                if meta:
                    return {"movie_results": [{"id": meta.get("id"), "title": meta.get("name")}]}
    except Exception:
        pass

    return None


# ------------------------------------------------------------------
# Genre mappings
# ------------------------------------------------------------------
GENRE_MAP: Dict[str, int] = {
    "Hành động": 28,
    "Phiêu lưu": 12,
    "Hoạt hình": 16,
    "Hài hước": 35,
    "Tội phạm": 80,
    "Tài liệu": 99,
    "Chính kịch": 18,
    "Gia đình": 10751,
    "Giả tưởng": 14,
    "Lịch sử": 36,
    "Kinh dị": 27,
    "Âm nhạc": 10402,
    "Bí ẩn": 9648,
    "Lãng mạn": 10749,
    "Khoa học viễn tưởng": 878,
    "Gây cấn": 53,
    "Chiến tranh": 10752,
    "Miền Tây": 37,
}

TV_GENRE_MAP: Dict[str, int] = {
    "Hành động": 10759,
    "Hoạt hình": 16,
    "Hài hước": 35,
    "Tội phạm": 80,
    "Tài liệu": 99,
    "Chính kịch": 18,
    "Gia đình": 10751,
    "Trẻ em": 10762,
    "Bí ẩn": 9648,
    "Tin tức": 10763,
    "Thực tế": 10764,
    "Khoa học viễn tưởng": 10765,
    "Soap": 10766,
    "Talk": 10767,
    "Chiến tranh": 10768,
    "Miền Tây": 37,
}

ALL_GENRE_OPTIONS = list(GENRE_MAP.keys())


# ------------------------------------------------------------------
# Manifest Builder
# ------------------------------------------------------------------
def get_ernax_manifest(api_key: str = "") -> Dict[str, Any]:
    query_suffix = f"?api_key={api_key}" if api_key else ""
    show_on_board = getattr(Config, "ENABLE_BOARD_ERNAX", True)
    main_req = not show_on_board

    return {
        "id": "community.ernax.stremio.addon",
        "version": "1.0.0",
        "name": "Ernax Player (ernax.pro)",
        "description": "Kho Phim Lẻ, Chiếu Rạp & TV Series Quốc Tế chất lượng 4K UHD, 1080p, 720p HLS trực tiếp từ Ernax (ernax.pro). Tích hợp giải mã tốc độ cao.",
        "logo": "https://ernax.pro/icon-512.png",
        "background": "https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=1920&auto=format&fit=crop&q=80",
        "resources": [
            "catalog",
            "meta",
            "stream",
        ] + ([
            {
                "name": "subtitles",
                "types": ["movie", "series"],
                "idPrefixes": ["ernax:", "tmdb:", "tt"],
            }
        ] if getattr(Config, "ENABLE_SUBTITLES", True) else []),
        "types": ["movie", "series"],
        "catalogs": [
            {
                "type": "movie",
                "id": "ernax_popular_movie",
                "name": "Ernax - Popular Movies",
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
                "id": "ernax_top_rated_movie",
                "name": "Ernax - Top Rated Movies",
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
                "id": "ernax_trending_movie",
                "name": "Ernax - Trending Movies",
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
                "id": "ernax_trending_series",
                "name": "Ernax - Trending TV Shows",
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
                "id": "ernax_popular_series",
                "name": "Ernax - Popular TV Shows",
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


@ernax_router.get("/ernax/manifest.json")
@ernax_router.get("/manifest.json")
async def ernax_manifest_endpoint():
    from config import Config
    if not getattr(Config, "ENABLE_SOURCE_ERNAX", True):
        raise HTTPException(status_code=404, detail="Ernax source is disabled.")
    return get_ernax_manifest()


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
    full_desc = "\n".join(desc_lines)

    stremio_id = f"ernax:{item_type}:{tmdb_id}"

    return {
        "id": stremio_id,
        "type": item_type,
        "name": f"✨ {title}",
        "poster": poster_url,
        "posterShape": "regular",
        "background": backdrop_url,
        "description": full_desc,
        "releaseInfo": year,
        "imdbRating": f"{vote_avg:.1f}" if vote_avg else None,
        "genres": ["Ernax 4K/HD"],
    }


@ernax_router.get("/ernax/catalog/{type}/{id}.json")
@ernax_router.get("/catalog/{type}/{id}.json")
@ernax_router.get("/ernax/catalog/{type}/{id}/{extra}.json")
@ernax_router.get("/catalog/{type}/{id}/{extra}.json")
async def ernax_catalog_endpoint(
    type: str,
    id: str,
    extra: Optional[str] = None,
    genre: Optional[str] = None,
    search: Optional[str] = None,
    skip: Optional[int] = 0,
):
    from config import Config
    if not getattr(Config, "ENABLE_SOURCE_ERNAX", True):
        return {"metas": []}

    # Parse extra params
    if extra:
        try:
            extra_dict = dict(urllib.parse.parse_qsl(extra))
            genre = genre or extra_dict.get("genre")
            search = search or extra_dict.get("search")
            if "skip" in extra_dict:
                try:
                    skip = int(extra_dict["skip"])
                except ValueError:
                    pass
        except Exception:
            pass

    page = (skip // 20) + 1 if skip else 1
    media_type = "movie" if type == "movie" else "tv"

    # Search mode
    if search:
        search_data = await ernax_fetch_tmdb_json(
            f"/search/{media_type}",
            params={"query": search, "page": page, "include_adult": "false"},
        )
        if search_data and search_data.get("results"):
            metas = [
                _format_tmdb_meta_item(item, type)
                for item in search_data["results"]
                if item.get("poster_path")
            ]
            return {"metas": metas}
        return {"metas": []}

    # Genre filter mode
    genre_id = None
    if genre and genre != "Tất cả":
        if media_type == "movie":
            genre_id = GENRE_MAP.get(genre)
        else:
            genre_id = TV_GENRE_MAP.get(genre) or GENRE_MAP.get(genre)

    if genre_id:
        discover_data = await ernax_fetch_tmdb_json(
            f"/discover/{media_type}",
            params={
                "with_genres": str(genre_id),
                "page": page,
                "sort_by": "popularity.desc",
                "vote_count.gte": "10",
                "include_adult": "false",
            },
        )
        if discover_data and discover_data.get("results"):
            metas = [
                _format_tmdb_meta_item(item, type)
                for item in discover_data["results"]
                if item.get("poster_path")
            ]
            return {"metas": metas}
        return {"metas": []}

    # Standard Catalogs
    endpoint = f"/{media_type}/popular"
    if "top_rated" in id:
        endpoint = f"/{media_type}/top_rated"
    elif "trending" in id:
        endpoint = f"/trending/{media_type}/week"

    catalog_data = await ernax_fetch_tmdb_json(endpoint, params={"page": page})
    if catalog_data and catalog_data.get("results"):
        metas = [
            _format_tmdb_meta_item(item, type)
            for item in catalog_data["results"]
            if item.get("poster_path")
        ]
        return {"metas": metas}

    return {"metas": []}


# ------------------------------------------------------------------
# Meta Handler
# ------------------------------------------------------------------
@ernax_router.get("/ernax/meta/{type}/{id}.json")
@ernax_router.get("/meta/{type}/{id}.json")
async def ernax_meta_endpoint(type: str, id: str):
    from config import Config
    if not getattr(Config, "ENABLE_SOURCE_ERNAX", True):
        raise HTTPException(status_code=404, detail="Ernax source is disabled.")

    media_type = "movie" if type == "movie" else "tv"
    tmdb_id: Optional[int] = None
    imdb_id: Optional[str] = None

    if id.startswith("ernax:"):
        parts = id.split(":")
        if len(parts) >= 3:
            media_type = "tv" if parts[1] == "series" else "movie"
            tmdb_id = int(parts[2])
    elif id.startswith("tmdb:"):
        parts = id.split(":")
        if len(parts) >= 2:
            tmdb_id = int(parts[1])
    elif id.startswith("tt"):
        # Resolve IMDb ID
        imdb_code = id.split(":")[0]
        imdb_id = imdb_code
        find_data = await ernax_fetch_tmdb_json(f"/find/{imdb_code}", params={"external_source": "imdb_id"})
        if find_data:
            if media_type == "tv" and find_data.get("tv_results"):
                tmdb_id = int(find_data["tv_results"][0]["id"])
            elif find_data.get("movie_results"):
                tmdb_id = int(find_data["movie_results"][0]["id"])
            elif find_data.get("tv_results"):
                tmdb_id = int(find_data["tv_results"][0]["id"])
                media_type = "tv"

    if not tmdb_id:
        raise HTTPException(status_code=404, detail="Media not found.")

    detail_data = await ernax_fetch_tmdb_json(
        f"/{media_type}/{tmdb_id}",
        params={"append_to_response": "credits,external_ids,videos"},
    )
    if not detail_data:
        raise HTTPException(status_code=404, detail="Metadata not found.")

    title = detail_data.get("title") or detail_data.get("name") or "Unknown Title"
    rel_date = detail_data.get("release_date") or detail_data.get("first_air_date") or ""
    year = rel_date[:4] if len(rel_date) >= 4 else ""
    poster_path = detail_data.get("poster_path")
    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
    backdrop_path = detail_data.get("backdrop_path")
    backdrop_url = f"https://image.tmdb.org/t/p/original{backdrop_path}" if backdrop_path else poster_url
    overview = detail_data.get("overview") or ""
    vote_avg = detail_data.get("vote_average", 0.0)
    runtime = detail_data.get("runtime") or (detail_data.get("episode_run_time") or [None])[0]

    genres = [g["name"] for g in detail_data.get("genres", []) if "name" in g]
    cast = [c["name"] for c in detail_data.get("credits", {}).get("cast", [])[:6] if "name" in c]
    directors = [
        c["name"]
        for c in detail_data.get("credits", {}).get("crew", [])
        if c.get("job") == "Director" and "name" in c
    ]

    trailer_yt = None
    for vid in detail_data.get("videos", {}).get("results", []):
        if vid.get("site") == "YouTube" and vid.get("type") in ["Trailer", "Teaser"]:
            trailer_yt = vid.get("key")
            break

    meta: Dict[str, Any] = {
        "id": id,
        "type": type,
        "name": f"✨ {title}",
        "poster": poster_url,
        "posterShape": "regular",
        "background": backdrop_url,
        "logo": poster_url,
        "description": overview,
        "releaseInfo": year,
        "imdbRating": f"{vote_avg:.1f}" if vote_avg else None,
        "genres": genres or ["Ernax 4K/HD"],
        "cast": cast,
        "director": directors,
        "runtime": f"{runtime} min" if runtime else None,
        "trailers": [{"source": trailer_yt, "type": "Trailer"}] if trailer_yt else [],
    }

    # If TV Series, fetch seasons & episodes
    if media_type == "tv":
        videos: List[Dict[str, Any]] = []
        seasons_list = detail_data.get("seasons", [])
        for s in seasons_list:
            s_num = s.get("season_number", 0)
            if s_num == 0:
                continue
            s_detail = await ernax_fetch_tmdb_json(f"/tv/{tmdb_id}/season/{s_num}")
            if s_detail and s_detail.get("episodes"):
                for ep in s_detail["episodes"]:
                    ep_num = ep.get("episode_number", 1)
                    ep_title = ep.get("name") or f"Tập {ep_num}"
                    ep_overview = ep.get("overview") or ""
                    ep_still = ep.get("still_path")
                    still_url = f"https://image.tmdb.org/t/p/w500{ep_still}" if ep_still else poster_url
                    ep_air = ep.get("air_date") or ""

                    videos.append({
                        "id": f"ernax:series:{tmdb_id}:{s_num}:{ep_num}",
                        "title": f"S{s_num:02d}E{ep_num:02d} - {ep_title}",
                        "season": s_num,
                        "episode": ep_num,
                        "released": ep_air,
                        "overview": ep_overview,
                        "thumbnail": still_url,
                    })

        if not videos and seasons_list:
            # Fallback simple episode numbering
            for s in seasons_list:
                s_num = s.get("season_number", 0)
                if s_num == 0:
                    continue
                ep_count = s.get("episode_count", 1)
                for ep_idx in range(1, ep_count + 1):
                    videos.append({
                        "id": f"ernax:series:{tmdb_id}:{s_num}:{ep_idx}",
                        "title": f"Mùa {s_num} Tập {ep_idx}",
                        "season": s_num,
                        "episode": ep_idx,
                    })
        meta["videos"] = videos

    return {"meta": meta}


# ------------------------------------------------------------------
# Stream Handler
# ------------------------------------------------------------------
@ernax_router.get("/ernax/stream/{type}/{id}.json")
@ernax_router.get("/stream/{type}/{id}.json")
async def ernax_stream_endpoint(type: str, id: str, request: Request = None):
    from config import Config
    if not getattr(Config, "ENABLE_SOURCE_ERNAX", True):
        return {"streams": []}

    base_url = Config.ADDON_URL.rstrip("/") if getattr(Config, "ADDON_URL", None) else (str(request.base_url).rstrip("/") if request else "http://127.0.0.1:7860")

    # Parse media details
    tmdb_id: Optional[int] = None
    media_type = "movie" if type == "movie" else "tv"
    season = 1
    episode = 1
    imdb_id = ""

    if id.startswith("ernax:"):
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
        find_data = await ernax_fetch_tmdb_json(f"/find/{imdb_code}", params={"external_source": "imdb_id"})
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
    detail_data = await ernax_fetch_tmdb_json(f"/{media_type}/{tmdb_id}", params={"append_to_response": "external_ids"})
    if not detail_data:
        return {"streams": []}

    title = detail_data.get("title") or detail_data.get("name") or "Movie"
    rel_date = detail_data.get("release_date") or detail_data.get("first_air_date") or ""
    year = rel_date[:4] if len(rel_date) >= 4 else ""
    if not imdb_id:
        imdb_id = detail_data.get("external_ids", {}).get("imdb_id", "")

    # Get dynamic session seed
    seed = await get_ernax_seed(tmdb_id)
    if not seed:
        return {"streams": []}

    # Web Embed Player link (for opening in browser directly)
    if media_type in ["tv", "series"]:
        embed_url = f"https://ernax.pro/tv/{tmdb_id}/{season}/{episode}"
    else:
        embed_url = f"https://ernax.pro/movie/{tmdb_id}"

    web_stream = {
        "name": "Ernax\n🌐 Web Player",
        "title": f"🎬 {title} {f'S{season:02d}E{episode:02d}' if (media_type in ['tv', 'series']) else ''}\n🌐 Xem trực tiếp trên Web (Ernax.pro Embed)\n🚀 0% Băng thông máy chủ | Nhấp để mở trên trình duyệt",
        "externalUrl": embed_url,
    }

    # Fetch and decrypt stream sources from Ernax CDN
    stream_payload = await fetch_ernax_stream_sources(
        tmdb_id=tmdb_id,
        media_type=media_type,
        title=title,
        year=year,
        imdb_id=imdb_id,
        season=season,
        episode=episode,
        seed=seed,
    )

    all_streams: List[Dict[str, Any]] = [web_stream]

    if stream_payload and isinstance(stream_payload, dict):
        master_playlist = stream_payload.get("playlist")
        sources_list = stream_payload.get("sources", [])
        subtitles_list = stream_payload.get("subtitles", [])

        # Format subtitles for Stremio
        formatted_subs: List[Dict[str, Any]] = []
        for idx, sub in enumerate(subtitles_list):
            sub_url = sub.get("url")
            lang = sub.get("lang") or sub.get("language") or f"Sub {idx + 1}"
            if sub_url:
                formatted_subs.append({
                    "id": f"ernax_sub_{idx}",
                    "url": sub_url,
                    "lang": lang,
                })

        proxy_base = f"{base_url}/ernax/stream_proxy"
        cdn_referer = "https://www.vidking.net/"
        encoded_referer = urllib.parse.quote(cdn_referer, safe="")

        # 1. Individual Resolution Streams (1080p FHD, 720p HD, 480p SD, 2160p 4K)
        for srv_src in sources_list:
            quality = str(srv_src.get("quality", "HD")).upper()
            src_url = srv_src.get("url")
            if not src_url:
                continue

            proxied_url = (
                f"{proxy_base}"
                f"?url={urllib.parse.quote(src_url, safe='')}"
                f"&referer={encoded_referer}"
            )

            icon = "💎" if ("2160" in quality or "4K" in quality) else ("🌟" if "1080" in quality else ("🎬" if "720" in quality else "📺"))
            all_streams.append({
                "name": f"Ernax\n{icon} {quality}",
                "title": (
                    f"🎬 {title} {f'S{season:02d}E{episode:02d}' if (media_type in ['tv', 'series']) else ''}\n"
                    f"{icon} Chất lượng: {quality} | HLS Stream\n"
                    f"🛡️ Proxy bảo vệ bản quyền & Tối ưu tua nhanh"
                ),
                "url": proxied_url,
                "behaviorHints": {
                    "notWebReady": True,
                    "bingeGroup": "ernax-hls",
                },
                "subtitles": formatted_subs,
            })

        # 2. Master Playlist M3U8 Stream (if available)
        if master_playlist:
            proxied_master = (
                f"{proxy_base}"
                f"?url={urllib.parse.quote(master_playlist, safe='')}"
                f"&referer={encoded_referer}"
            )
            all_streams.append({
                "name": "Ernax\n⚡ Auto Master",
                "title": (
                    f"🎬 {title} {f'S{season:02d}E{episode:02d}' if (media_type in ['tv', 'series']) else ''}\n"
                    f"⚡ Master HLS Stream (Tự thích ứng 4K / 1080p / 720p / 480p)\n"
                    f"🛡️ Hỗ trợ phụ đề đa ngữ | Tốc độ tải tối đa"
                ),
                "url": proxied_master,
                "behaviorHints": {
                    "notWebReady": True,
                    "bingeGroup": "ernax-hls",
                },
                "subtitles": formatted_subs,
            })

    # Sort streams: Web Player top, then 2160p/4K > 1080p > 720p > 480p > Master
    def quality_score(item: Dict[str, Any]) -> int:
        if "externalUrl" in item:
            return 999
        title_str = item.get("title", "") + item.get("name", "")
        base_score = 50
        if "2160" in title_str or "4K" in title_str:
            base_score = 400
        elif "1080" in title_str:
            base_score = 300
        elif "720" in title_str:
            base_score = 200
        elif "480" in title_str:
            base_score = 100
        elif "Master" in title_str or "Auto" in title_str:
            base_score = 50
        return base_score

    all_streams.sort(key=quality_score, reverse=True)
    return {"streams": all_streams}


# ------------------------------------------------------------------
# Stream Proxy Handler (Referer & CORS bypass)
# ------------------------------------------------------------------
@ernax_router.get("/ernax/stream_proxy")
@ernax_router.get("/stream_proxy")
async def ernax_stream_proxy(
    request: Request,
    url: str,
    referer: Optional[str] = "https://www.vidking.net/",
):
    """Proxies HLS playlists (.m3u8) and video segments (.ts, .m4s, .mp4) with proper Referer & CORS."""
    from fastapi.responses import StreamingResponse

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

    is_m3u8 = url.endswith(".m3u8")

    try:
        if is_m3u8:
            # For M3U8 playlists: fetch fully, rewrite URLs, return
            client = get_ernax_client()
            res = await client.get(url, headers=headers)
            if res.status_code != 200:
                return Response(
                    content=res.content,
                    status_code=res.status_code,
                    headers={"Access-Control-Allow-Origin": "*"},
                )

            from config import Config
            app_base_url = Config.ADDON_URL.rstrip("/") if getattr(Config, "ADDON_URL", None) else str(request.base_url).rstrip("/")
            proxy_endpoint = (
                f"{app_base_url}/ernax/stream_proxy"
                if not app_base_url.endswith("/ernax")
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
                "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                "Cache-Control": "no-cache",
            }
            return Response(content=body, headers=resp_headers)

        # For media segments (.ts, .m4s, .mp4): use streaming response
        # Create a dedicated client for streaming to avoid blocking the shared client
        stream_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=6.0),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=30, max_connections=60),
        )

        upstream_resp = await stream_client.send(
            stream_client.build_request("GET", url, headers=headers),
            stream=True,
        )

        if upstream_resp.status_code not in (200, 206):
            body = await upstream_resp.aread()
            await upstream_resp.aclose()
            await stream_client.aclose()
            return Response(
                content=body,
                status_code=upstream_resp.status_code,
                headers={"Access-Control-Allow-Origin": "*"},
            )

        content_type = upstream_resp.headers.get("content-type", "")

        resp_headers = {
            "Content-Type": content_type or "video/MP2T",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Accept-Ranges": "bytes",
        }
        for hdr in ["content-range", "content-length", "accept-ranges"]:
            if hdr in upstream_resp.headers:
                resp_headers[hdr] = upstream_resp.headers[hdr]

        async def stream_generator():
            try:
                async for chunk in upstream_resp.aiter_bytes(chunk_size=256 * 1024):
                    yield chunk
            finally:
                await upstream_resp.aclose()
                await stream_client.aclose()

        return StreamingResponse(
            stream_generator(),
            status_code=upstream_resp.status_code,
            headers=resp_headers,
            media_type=resp_headers["Content-Type"],
        )
    except Exception as e:
        logger.error(f"[Ernax] Proxy error for {url}: {e}")
        raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}")


# ------------------------------------------------------------------
# Subtitles Handler
# ------------------------------------------------------------------
@ernax_router.get("/ernax/subtitles/{type}/{id}.json")
@ernax_router.get("/subtitles/{type}/{id}.json")
@ernax_router.get("/ernax/subtitles/{type}/{id}/{extra}.json")
@ernax_router.get("/subtitles/{type}/{id}/{extra}.json")
async def ernax_subtitles_endpoint(type: str, id: str, extra: Optional[str] = None):
    from config import Config
    if not getattr(Config, "ENABLE_SOURCE_ERNAX", True) or not getattr(Config, "ENABLE_SUBTITLES", True):
        return {"subtitles": []}

    media_type = "movie" if type == "movie" else "tv"
    tmdb_id: Optional[int] = None
    season = 1
    episode = 1
    imdb_id = ""

    if id.startswith("ernax:"):
        parts = id.split(":")
        if len(parts) >= 5:
            media_type = "tv" if parts[1] == "series" else "movie"
            tmdb_id = int(parts[2])
            season = int(parts[3])
            episode = int(parts[4])
        elif len(parts) >= 3:
            media_type = "tv" if parts[1] == "series" else "movie"
            tmdb_id = int(parts[2])
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
        parts = id.split(":")
        imdb_code = parts[0]
        if len(parts) >= 3:
            season = int(parts[1])
            episode = int(parts[2])
            media_type = "tv"
        imdb_id = imdb_code
        find_data = await ernax_fetch_tmdb_json(f"/find/{imdb_code}", params={"external_source": "imdb_id"})
        if find_data:
            if media_type == "tv" and find_data.get("tv_results"):
                tmdb_id = int(find_data["tv_results"][0]["id"])
            elif find_data.get("movie_results"):
                tmdb_id = int(find_data["movie_results"][0]["id"])

    if not tmdb_id:
        return {"subtitles": []}

    # Fetch sources and extract embedded subtitles
    stream_payload = await fetch_ernax_stream_sources(
        tmdb_id=tmdb_id,
        media_type=media_type,
        season=season,
        episode=episode,
        imdb_id=imdb_id,
    )

    if not stream_payload or not stream_payload.get("subtitles"):
        return {"subtitles": []}

    subs_out: List[Dict[str, Any]] = []
    for idx, sub in enumerate(stream_payload["subtitles"]):
        sub_url = sub.get("url")
        lang = sub.get("lang") or sub.get("language") or f"Sub {idx + 1}"
        if sub_url:
            subs_out.append({
                "id": f"ernax_sub_{idx}",
                "url": sub_url,
                "lang": lang,
            })

    return {"subtitles": subs_out}


# ------------------------------------------------------------------
# Aggregated Search Function (For Dashboard Integration)
# ------------------------------------------------------------------
async def ernax_search(query: str, max_results: int = 15) -> List[Dict[str, Any]]:
    """Searches Ernax / TMDB catalog for dashboard search aggregation."""
    from config import Config
    if not getattr(Config, "ENABLE_SOURCE_ERNAX", True) or not query.strip():
        return []

    results = []
    # Search both movies & tv series concurrently
    tasks = [
        ernax_fetch_tmdb_json("/search/movie", params={"query": query.strip(), "page": 1}),
        ernax_fetch_tmdb_json("/search/tv", params={"query": query.strip(), "page": 1}),
    ]
    res_list = await asyncio.gather(*tasks, return_exceptions=True)

    for idx, res in enumerate(res_list):
        if isinstance(res, dict) and res.get("results"):
            item_type = "movie" if idx == 0 else "series"
            for item in res["results"][:max_results]:
                tmdb_id = item.get("id")
                title = item.get("title") or item.get("name") or "Unknown Title"
                rel_date = item.get("release_date") or item.get("first_air_date") or ""
                year = rel_date[:4] if len(rel_date) >= 4 else ""
                poster_path = item.get("poster_path")
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
                vote_avg = item.get("vote_average", 0.0)

                results.append({
                    "id": f"ernax:{item_type}:{tmdb_id}",
                    "title": title,
                    "name": title,
                    "year": year,
                    "type": item_type,
                    "poster": poster_url,
                    "vote_average": vote_avg,
                    "source": "ernax",
                    "source_name": "Ernax Player (4K/HD)",
                })

    return results[:max_results]
