"""
Performance and HTTP helper layer for UHDMovies addon.

Features:
* Shared httpx.AsyncClient with HTTP/2 and keep-alive
* Mirror racing with active base pinning
* Multi-level TTL cache with LRU eviction, single-flight deduplication, and disk persistence
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

logger = logging.getLogger("uhdmovies_addon")


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


CONNECT_TIMEOUT = _env_float("UHD_CONNECT_TIMEOUT", 5.0)
READ_TIMEOUT = _env_float("UHD_READ_TIMEOUT", 15.0)
POOL_TIMEOUT = _env_float("UHD_POOL_TIMEOUT", 5.0)
MAX_CONNECTIONS = _env_int("UHD_MAX_CONNECTIONS", 40)
MAX_KEEPALIVE = _env_int("UHD_MAX_KEEPALIVE", 20)
KEEPALIVE_EXPIRY = _env_float("UHD_KEEPALIVE_EXPIRY", 90.0)
REQUEST_RETRIES = _env_int("UHD_REQUEST_RETRIES", 1)

CACHE_TTL = _env_int("UHD_CACHE_TTL", 300)
NEGATIVE_TTL = _env_int("UHD_NEGATIVE_TTL", 60)
STREAM_CACHE_TTL = _env_int("UHD_STREAM_CACHE_TTL", 1800)
CACHE_MAX_ENTRIES = _env_int("UHD_CACHE_MAX_ENTRIES", 2000)
CACHE_SAVE_INTERVAL = _env_float("UHD_CACHE_SAVE_INTERVAL", 15.0)
CACHE_PERSIST_MIN_TTL = _env_int("UHD_CACHE_PERSIST_MIN_TTL", 600)
CACHE_FILE = os.getenv("UHD_CACHE_FILE") or os.path.join(
    tempfile.gettempdir(), "uhdmovies_cache.json"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
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
# Shared HTTP Client
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
    )


async def get_client() -> httpx.AsyncClient:
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


async def close_client() -> None:
    global _CLIENT
    async with _client_lock():
        if _CLIENT is not None and not _CLIENT.is_closed:
            try:
                await _CLIENT.aclose()
            except Exception:
                pass
        _CLIENT = None


# ------------------------------------------------------------------
# Cache System with Disk Persistence & Single-Flight Dedup
# ------------------------------------------------------------------
CACHE: OrderedDict = OrderedDict()
_LOCKS: Dict[str, asyncio.Lock] = {}
_LAST_SAVE: float = 0.0
_SAVE_LOCK: Optional[asyncio.Lock] = None


def _save_lock() -> asyncio.Lock:
    global _SAVE_LOCK
    if _SAVE_LOCK is None:
        _SAVE_LOCK = asyncio.Lock()
    return _SAVE_LOCK


def _entry_lock(key: str) -> asyncio.Lock:
    lock = _LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[key] = lock
    return lock


def get_cached(key: str) -> Tuple[Optional[Any], bool]:
    """Return (value, is_hit). Supports stale-while-revalidate."""
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

        stale_val, _ = get_cached(key)

        try:
            res = await factory()
        except Exception as e:
            logger.exception(f"Factory error for key {key}: {e}")
            res = None

        if res is not None:
            set_cached(key, res, ttl=ttl, stale_ttl=stale_ttl)
            schedule_cache_save()
            return res

        if stale_val is not None:
            set_cached(key, stale_val, ttl=negative_ttl)
            return stale_val

        if negative_ttl > 0:
            set_cached(key, None, ttl=negative_ttl)
        return None


def save_cache_sync() -> None:
    now = time.time()
    persist: Dict[str, Any] = {}
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
        logger.debug(f"Could not persist UHDMovies cache to {CACHE_FILE}: {e}")


async def save_cache() -> None:
    global _LAST_SAVE
    async with _save_lock():
        now = time.time()
        if now - _LAST_SAVE < CACHE_SAVE_INTERVAL:
            return
        _LAST_SAVE = now
        await asyncio.to_thread(save_cache_sync)


def schedule_cache_save() -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(save_cache())
    except RuntimeError:
        pass


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
        logger.info(f"Loaded {len(CACHE)} cached items for UHDMovies from disk.")
    except Exception as e:
        logger.warning(f"Failed to load UHDMovies cache from {CACHE_FILE}: {e}")


load_cache()


# ------------------------------------------------------------------
# Mirror & Base URL Management
# ------------------------------------------------------------------
UHDMOVIES_BASE_DEFAULT = (
    os.getenv("UHDMOVIES_BASE_URL") or "https://uhdmovies.autos"
).rstrip("/")
UHDMOVIES_BACKUP_URLS: List[str] = [
    UHDMOVIES_BASE_DEFAULT,
    "https://uhdmovies.autos",
]

_ACTIVE_BASE: str = UHDMOVIES_BASE_DEFAULT


def get_active_base(fallback: str = UHDMOVIES_BASE_DEFAULT) -> str:
    global _ACTIVE_BASE
    return _ACTIVE_BASE or fallback


def note_active_base(base: str) -> None:
    global _ACTIVE_BASE
    if base and base.startswith("http"):
        _ACTIVE_BASE = base.rstrip("/")


def base_of(url: str, bases: Iterable[str]) -> Optional[str]:
    for b in bases:
        if url.startswith(b):
            return b
    return None


def mirror_candidates(
    url: str,
    bases: Iterable[str] = UHDMOVIES_BACKUP_URLS,
    default_base: str = UHDMOVIES_BASE_DEFAULT,
) -> List[str]:
    current = base_of(url, bases) or default_base
    tail = url[len(current) :] if url.startswith(current) else url
    active = get_active_base(default_base)
    ordered = [active] + [b for b in bases if b != active]
    # Remove duplicates preserving order
    seen = set()
    result = []
    for b in ordered:
        if b not in seen:
            seen.add(b)
            result.append(b.rstrip("/") + ("/" + tail.lstrip("/") if tail else ""))
    return result


def is_content_valid(text: Optional[str]) -> bool:
    if not text or len(text) < 10000:
        return False
    t = text.lower()
    return any(marker in t for marker in ("gridlove", "entry-content", "article", "post-", "hentry"))


# ------------------------------------------------------------------
# Fetch Helpers with Race & Retry
# ------------------------------------------------------------------
async def fetch_text(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = READ_TIMEOUT,
    retries: int = REQUEST_RETRIES,
) -> Optional[str]:
    client = await get_client()
    req_headers = dict(DEFAULT_HEADERS)
    if headers:
        req_headers.update(headers)

    for attempt in range(retries + 1):
        try:
            resp = await client.get(url, headers=req_headers, timeout=timeout, follow_redirects=True)
            logger.info("fetch_text %s -> status=%s, len=%s", url, resp.status_code, len(resp.text) if resp.text else 0)
            if resp.status_code == 200 and resp.text:
                return resp.text
            if resp.status_code in (404, 410):
                return None
        except httpx.RequestError as e:
            logger.info("fetch_text RequestError %s: %s", url, e)
            if attempt == retries:
                logger.debug(f"fetch_text failed for {url}: {e}")
                return None
            await asyncio.sleep(0.3 * (attempt + 1))
        except Exception as e:
            logger.info("fetch_text Exception %s: %s", url, e)
            logger.debug(f"fetch_text unexpected error for {url}: {e}")
            return None
    return None


async def fetch_json(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = READ_TIMEOUT,
) -> Optional[Any]:
    text = await fetch_text(url, headers=headers, timeout=timeout)
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


async def race_fetch_text(
    urls: List[str],
    headers: Optional[Dict[str, str]] = None,
    timeout: float = READ_TIMEOUT,
) -> Tuple[Optional[str], Optional[str]]:
    """Race multiple mirror URLs concurrently, returning (winning_text, winning_url)."""
    if not urls:
        return None, None
    if len(urls) == 1:
        text = await fetch_text(urls[0], headers=headers, timeout=timeout)
        return (text, urls[0]) if text else (None, None)

    client = await get_client()
    req_headers = dict(DEFAULT_HEADERS)
    if headers:
        req_headers.update(headers)

    tasks = [
        asyncio.create_task(
            client.get(u, headers=req_headers, timeout=timeout, follow_redirects=True)
        )
        for u in urls
    ]

    for future in asyncio.as_completed(tasks):
        try:
            resp = await future
            if resp.status_code == 200 and resp.text and is_content_valid(resp.text):
                # Cancel remaining tasks
                for t in tasks:
                    if not t.done():
                        t.cancel()
                winning_url = str(resp.url)
                return resp.text, winning_url
        except Exception:
            continue

    return None, None
