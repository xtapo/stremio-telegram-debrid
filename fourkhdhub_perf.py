"""
Performance and HTTP helper layer for 4KHDHub addon.

Features:
* Shared httpx.AsyncClient with keep-alive and event loop safety
* Mirror racing with active base pinning
* Multi-level TTL cache with LRU eviction, single-flight entry locks, and disk persistence
* Fast HTML parsing with lxml fallback
"""

import asyncio
import datetime
import json
import logging
import os
import tempfile
import time
import urllib.parse
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup, SoupStrainer

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

logger = logging.getLogger("fourkhdhub_addon")


# ------------------------------------------------------------------
# Environment Knobs & Defaults
# ------------------------------------------------------------------
def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return float(default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _env_int(name: str, default: int) -> int:
    return int(_env_float(name, float(default)))


CONNECT_TIMEOUT = _env_float("FOURKHD_CONNECT_TIMEOUT", 5.0)
READ_TIMEOUT = _env_float("FOURKHD_READ_TIMEOUT", 15.0)
POOL_TIMEOUT = _env_float("FOURKHD_POOL_TIMEOUT", 5.0)
MAX_CONNECTIONS = _env_int("FOURKHD_MAX_CONNECTIONS", 40)
MAX_KEEPALIVE = _env_int("FOURKHD_MAX_KEEPALIVE", 20)
KEEPALIVE_EXPIRY = _env_float("FOURKHD_KEEPALIVE_EXPIRY", 90.0)
REQUEST_RETRIES = _env_int("FOURKHD_REQUEST_RETRIES", 1)

CACHE_TTL = _env_int("FOURKHD_CACHE_TTL", 300)
NEGATIVE_TTL = _env_int("FOURKHD_NEGATIVE_TTL", 60)
STREAM_CACHE_TTL = _env_int("FOURKHD_STREAM_CACHE_TTL", 1800)
CACHE_MAX_ENTRIES = _env_int("FOURKHD_CACHE_MAX_ENTRIES", 2000)
CACHE_SAVE_INTERVAL = _env_float("FOURKHD_CACHE_SAVE_INTERVAL", 15.0)
CACHE_PERSIST_MIN_TTL = _env_int("FOURKHD_CACHE_PERSIST_MIN_TTL", 600)
CACHE_FILE = os.getenv("FOURKHD_CACHE_FILE") or os.path.join(
    tempfile.gettempdir(), "fourkhdhub_cache.json"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ------------------------------------------------------------------
# HTML Parser
# ------------------------------------------------------------------
try:
    import lxml  # noqa: F401

    HTML_PARSER = "lxml"
except Exception:
    HTML_PARSER = "html.parser"


def make_soup(markup: str, only: Optional[SoupStrainer] = None) -> BeautifulSoup:
    if not markup:
        return BeautifulSoup("", HTML_PARSER)
    if only is not None:
        try:
            soup = BeautifulSoup(markup, HTML_PARSER, parse_only=only)
            if soup.contents:
                return soup
        except Exception:
            pass
    return BeautifulSoup(markup, HTML_PARSER)


# ------------------------------------------------------------------
# Shared Async HTTP Client
# ------------------------------------------------------------------
_CLIENT: Optional[httpx.AsyncClient] = None
_CLIENT_LOOP: Optional[asyncio.AbstractEventLoop] = None
_CLIENT_LOCK: Optional[asyncio.Lock] = None


def _client_lock() -> asyncio.Lock:
    global _CLIENT_LOCK
    if _CLIENT_LOCK is None:
        _CLIENT_LOCK = asyncio.Lock()
    return _CLIENT_LOCK


def _build_client(http2: bool = False) -> httpx.AsyncClient:
    limits = httpx.Limits(
        max_connections=MAX_CONNECTIONS,
        max_keepalive_connections=MAX_KEEPALIVE,
        keepalive_expiry=KEEPALIVE_EXPIRY,
    )
    timeout = httpx.Timeout(
        READ_TIMEOUT,
        connect=CONNECT_TIMEOUT,
        pool=POOL_TIMEOUT,
    )
    return httpx.AsyncClient(
        http2=http2,
        limits=limits,
        timeout=timeout,
        follow_redirects=True,
        headers=DEFAULT_HEADERS,
        verify=False,
    )


async def get_http_client() -> httpx.AsyncClient:
    global _CLIENT, _CLIENT_LOOP
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _CLIENT is not None and not _CLIENT.is_closed and _CLIENT_LOOP is current_loop:
        return _CLIENT
    async with _client_lock():
        if _CLIENT is not None and not _CLIENT.is_closed and _CLIENT_LOOP is current_loop:
            return _CLIENT
        _CLIENT = _build_client(http2=False)
        _CLIENT_LOOP = current_loop
        return _CLIENT


async def close_http_client() -> None:
    global _CLIENT
    async with _client_lock():
        if _CLIENT is not None and not _CLIENT.is_closed:
            try:
                await _CLIENT.aclose()
            except Exception:
                pass
        _CLIENT = None


# ------------------------------------------------------------------
# Base URL & Mirrors Management
# ------------------------------------------------------------------
FOURKHDHUB_BASE_DEFAULT = os.getenv(
    "FOURKHDHUB_BASE_URL", "https://4khdhub.one"
).rstrip("/")

FOURKHDHUB_BACKUP_URLS = [
    FOURKHDHUB_BASE_DEFAULT,
    "https://4khdhub.one",
    "https://4khdhub.com",
]

_ACTIVE_BASE: str = FOURKHDHUB_BASE_DEFAULT
_ACTIVE_BASE_EXPIRY: float = 0.0
ACTIVE_BASE_TTL: float = 600.0


def base_of(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".rstrip("/")


def get_active_base(fallback: Optional[str] = None) -> str:
    global _ACTIVE_BASE, _ACTIVE_BASE_EXPIRY
    if time.time() < _ACTIVE_BASE_EXPIRY and _ACTIVE_BASE:
        return _ACTIVE_BASE
    return fallback or FOURKHDHUB_BASE_DEFAULT


def note_active_base(base: str) -> None:
    global _ACTIVE_BASE, _ACTIVE_BASE_EXPIRY
    if not base:
        return
    clean = base.rstrip("/")
    if clean != _ACTIVE_BASE:
        logger.info("Switching active 4KHDHub base to %s", clean)
    _ACTIVE_BASE = clean
    _ACTIVE_BASE_EXPIRY = time.time() + ACTIVE_BASE_TTL


def mirror_candidates(path_or_url: str, bases: Optional[List[str]] = None) -> List[str]:
    active = get_active_base()
    all_bases: List[str] = [active]
    for b in bases or FOURKHDHUB_BACKUP_URLS:
        if b and b not in all_bases:
            all_bases.append(b)

    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        parts = urllib.parse.urlsplit(path_or_url)
        path = parts.path
        if parts.query:
            path += "?" + parts.query
    else:
        path = "/" + path_or_url.lstrip("/")

    urls = []
    for b in all_bases:
        urls.append(b.rstrip("/") + path)
    return urls


# ------------------------------------------------------------------
# Cache System
# ------------------------------------------------------------------
CACHE: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_LOCKS: Dict[str, asyncio.Lock] = {}
_LAST_SAVE: float = 0.0


def _entry_lock(key: str) -> asyncio.Lock:
    lock = _LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[key] = lock
    return lock


def get_cached(key: str) -> Tuple[Optional[Any], bool]:
    now = time.time()
    entry = CACHE.get(key)
    if entry is None:
        return None, False
    expires_at = entry.get("expires_at", 0)
    stale_until = entry.get("stale_until", expires_at)
    if now <= expires_at:
        try:
            CACHE.move_to_end(key)
        except Exception:
            pass
        return entry.get("data"), True
    if now <= stale_until:
        return entry.get("data"), False
    try:
        del CACHE[key]
    except KeyError:
        pass
    return None, False


def set_cached(
    key: str,
    data: Any,
    ttl: int = CACHE_TTL,
    stale_ttl: Optional[int] = None,
) -> None:
    now = time.time()
    stale_after = ttl if stale_ttl is None else max(ttl, stale_ttl)
    CACHE[key] = {
        "data": data,
        "expires_at": now + ttl,
        "stale_until": now + stale_after,
    }
    try:
        CACHE.move_to_end(key)
    except Exception:
        pass
    while len(CACHE) > CACHE_MAX_ENTRIES:
        try:
            CACHE.popitem(last=False)
        except Exception:
            break


async def cached_call(
    key: str,
    factory: Callable[[], Awaitable[Any]],
    ttl: int = CACHE_TTL,
    stale_ttl: Optional[int] = None,
    negative_ttl: int = NEGATIVE_TTL,
) -> Any:
    val, hit = get_cached(key)
    if hit and val is not None:
        return val

    async with _entry_lock(key):
        val, hit = get_cached(key)
        if hit and val is not None:
            return val

        try:
            res = await factory()
        except Exception as e:
            logger.exception(f"Factory error for key {key}: {e}")
            res = None

        use_ttl = negative_ttl if (res is None or res == [] or res == {}) else ttl
        set_cached(key, res, ttl=use_ttl, stale_ttl=stale_ttl)
        schedule_cache_save()
        return res


# ------------------------------------------------------------------
# Fetch Helpers
# ------------------------------------------------------------------
async def fetch_text(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    referer: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Tuple[Optional[str], Optional[str]]:
    client = await get_http_client()
    req_headers = dict(DEFAULT_HEADERS)
    if headers:
        req_headers.update(headers)
    if referer:
        req_headers["Referer"] = referer

    try:
        resp = await client.get(url, headers=req_headers, timeout=timeout or READ_TIMEOUT)
        if resp.status_code == 200:
            return resp.text, str(resp.url)
        logger.debug("fetch_text %s returned %s", url, resp.status_code)
        return None, None
    except Exception as e:
        logger.debug("fetch_text %s failed: %s", url, e)
        return None, None


async def race_fetch_text(
    candidates: List[str],
    headers: Optional[Dict[str, str]] = None,
    referer: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    if not candidates:
        return None, None
    if len(candidates) == 1:
        return await fetch_text(candidates[0], headers=headers, referer=referer)

    tasks = [
        asyncio.create_task(fetch_text(u, headers=headers, referer=referer))
        for u in candidates
    ]
    done_iter = asyncio.as_completed(tasks)
    try:
        for fut in done_iter:
            try:
                text, final_url = await fut
                if text:
                    for t in tasks:
                        if not t.done():
                            t.cancel()
                    if final_url:
                        note_active_base(base_of(final_url))
                    return text, final_url
            except Exception:
                continue
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
    return None, None


async def fetch_json(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
) -> Optional[Any]:
    text, _ = await fetch_text(url, headers=headers, timeout=timeout)
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


# ------------------------------------------------------------------
# Cache Persistence
# ------------------------------------------------------------------
def save_cache_sync() -> None:
    now = time.time()
    persist = {}
    for k, v in list(CACHE.items()):
        exp = v.get("expires_at", 0)
        if exp - now >= CACHE_PERSIST_MIN_TTL and v.get("data") is not None:
            try:
                json.dumps(v.get("data"))
                persist[k] = v
            except Exception:
                pass
    try:
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(persist, f)
        os.replace(tmp, CACHE_FILE)
    except Exception as e:
        logger.debug(f"Could not persist 4KHDHub cache to {CACHE_FILE}: {e}")


def schedule_cache_save() -> None:
    pass


def save_cache() -> None:
    save_cache_sync()


def load_cache() -> None:
    if not os.path.exists(CACHE_FILE):
        return
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        now = time.time()
        for k, v in loaded.items():
            if isinstance(v, dict) and v.get("expires_at", 0) > now:
                CACHE[k] = v
        logger.info(f"Loaded {len(CACHE)} cached items for 4KHDHub from disk.")
    except Exception as e:
        logger.warning(f"Failed to load 4KHDHub cache from {CACHE_FILE}: {e}")


load_cache()
