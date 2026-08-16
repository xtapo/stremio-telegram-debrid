"""
Performance and HTTP helper layer for HDHub4u addon.

Features:
* Shared httpx.AsyncClient with HTTP/2 and keep-alive
* Dynamic host resolution (querying HDHub4u host APIs & active mirrors)
* Fast mirror racing with active base pinning
* Multi-level TTL cache with LRU eviction, single-flight deduplication, and disk persistence
* Fast HTML parsing with lxml fallback
"""

import asyncio
import base64
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

logger = logging.getLogger("hdhub4u_addon")


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


CONNECT_TIMEOUT = _env_float("HDH_CONNECT_TIMEOUT", 4.0)
READ_TIMEOUT = _env_float("HDH_READ_TIMEOUT", 12.0)
POOL_TIMEOUT = _env_float("HDH_POOL_TIMEOUT", 5.0)
MAX_CONNECTIONS = _env_int("HDH_MAX_CONNECTIONS", 40)
MAX_KEEPALIVE = _env_int("HDH_MAX_KEEPALIVE", 20)
KEEPALIVE_EXPIRY = _env_float("HDH_KEEPALIVE_EXPIRY", 90.0)
REQUEST_RETRIES = _env_int("HDH_REQUEST_RETRIES", 1)

CACHE_TTL = _env_int("HDH_CACHE_TTL", 300)
NEGATIVE_TTL = _env_int("HDH_NEGATIVE_TTL", 60)
STREAM_CACHE_TTL = _env_int("HDH_STREAM_CACHE_TTL", 1800)
CACHE_MAX_ENTRIES = _env_int("HDH_CACHE_MAX_ENTRIES", 2000)
CACHE_SAVE_INTERVAL = _env_float("HDH_CACHE_SAVE_INTERVAL", 15.0)
CACHE_PERSIST_MIN_TTL = _env_int("HDH_CACHE_PERSIST_MIN_TTL", 600)
CACHE_FILE = os.getenv("HDH_CACHE_FILE") or os.path.join(
    tempfile.gettempdir(), "hdhub4u_cache.json"
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
_CLIENT_LOCK: Optional[asyncio.Lock] = None
_HTTP2_ENABLED = True


def _client_lock() -> asyncio.Lock:
    global _CLIENT_LOCK
    if _CLIENT_LOCK is None:
        _CLIENT_LOCK = asyncio.Lock()
    return _CLIENT_LOCK


def _build_client(http2: bool = True) -> httpx.AsyncClient:
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
    global _CLIENT, _HTTP2_ENABLED
    if _CLIENT is not None and not _CLIENT.is_closed:
        return _CLIENT
    async with _client_lock():
        if _CLIENT is not None and not _CLIENT.is_closed:
            return _CLIENT
        try:
            _CLIENT = _build_client(http2=_HTTP2_ENABLED)
        except Exception as e:
            logger.warning(f"HTTP/2 init failed, falling back to HTTP/1.1: {e}")
            _HTTP2_ENABLED = False
            _CLIENT = _build_client(http2=False)
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
    if hit:
        return val

    async with _entry_lock(key):
        val, hit = get_cached(key)
        if hit:
            return val

        stale_val, _ = get_cached(key)

        try:
            res = await factory()
        except Exception as e:
            logger.debug(f"Factory error for key {key}: {e}")
            res = None

        if res:
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
        logger.debug(f"Could not persist HDHub4u cache to {CACHE_FILE}: {e}")


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
        asyncio.create_task(save_cache())
    except RuntimeError:
        pass


def restore_cache_from_disk() -> int:
    if not os.path.exists(CACHE_FILE):
        return 0
    now = time.time()
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        count = 0
        for k, v in raw.items():
            if isinstance(v, dict) and v.get("expires_at", 0) > now:
                CACHE[k] = v
                count += 1
        if count:
            logger.info(f"Restored {count} HDHub4u cache entries from disk")
        return count
    except Exception as e:
        logger.debug(f"Could not read HDHub4u cache from {CACHE_FILE}: {e}")
        return 0


# ------------------------------------------------------------------
# Dynamic Mirror & Host Resolution
# ------------------------------------------------------------------
HDHUB4U_BASE_DEFAULT = "https://new1.hdhub4u.af"
HDHUB4U_BACKUP_URLS = [
    "https://new1.hdhub4u.af",
]

HOST_RESOLVER_URLS = [
    "https://h4.suncdn.org/host/",
    "https://points.topapii.com/host/",
    "https://ml.theapii.org/host/",
    "https://dns.pingora.fyi/v2/host",
]

_ACTIVE_BASE: Optional[str] = None
_ACTIVE_BASE_EXPIRY: float = 0.0


def is_landing_page(text: str) -> bool:
    if not text:
        return True
    return "Brief overview of HDHub4u website" in text or "How HDHub4u Stands Out" in text


def note_active_base(base: str) -> None:
    global _ACTIVE_BASE, _ACTIVE_BASE_EXPIRY
    if base and base.startswith("http") and "hdhub4u.bi" not in base:
        _ACTIVE_BASE = base.rstrip("/")
        _ACTIVE_BASE_EXPIRY = time.time() + 900.0


def get_active_base(default: str = HDHUB4U_BASE_DEFAULT) -> str:
    global _ACTIVE_BASE, _ACTIVE_BASE_EXPIRY
    if _ACTIVE_BASE and time.time() < _ACTIVE_BASE_EXPIRY:
        return _ACTIVE_BASE
    return default.rstrip("/")


async def resolve_dynamic_host() -> str:
    """Fetch current dynamic host for HDHub4u from host API services."""
    active = get_active_base("")
    if active:
        return active

    client = await get_client()
    t = datetime.datetime.now()
    v = 1000000 * t.year + 10000 * t.month + 100 * t.day + t.hour + 1

    for api_url in HOST_RESOLVER_URLS:
        try:
            r = await client.get(f"{api_url}?v={v}", timeout=3.5)
            if r.status_code == 200:
                data = r.json()
                if "c" in data:
                    raw_c = base64.b64decode(data["c"]).decode("utf-8", "ignore")
                    parsed = urllib.parse.urlsplit(raw_c)
                    resolved_base = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
                    if resolved_base.startswith("http") and "hdhub4u.bi" not in resolved_base:
                        note_active_base(resolved_base)
                        if resolved_base not in HDHUB4U_BACKUP_URLS:
                            HDHUB4U_BACKUP_URLS.insert(0, resolved_base)
                        logger.info(f"Resolved HDHub4u dynamic host: {resolved_base}")
                        return resolved_base
        except Exception:
            continue

    note_active_base(HDHUB4U_BASE_DEFAULT)
    return HDHUB4U_BASE_DEFAULT


def base_of(url: str, bases: Iterable[str]) -> Optional[str]:
    for b in bases:
        if url.startswith(b):
            return b
    return None


def mirror_candidates(url: str, bases: List[str], primary: str) -> List[str]:
    active = get_active_base(primary)
    ordered_bases: List[str] = [active]
    for b in bases:
        if b not in ordered_bases and "hdhub4u.bi" not in b:
            ordered_bases.append(b)

    original_base = base_of(url, ordered_bases)
    if not original_base:
        return [url]

    path = url[len(original_base):]
    return [b.rstrip("/") + path for b in ordered_bases]


async def race_fetch_text(
    urls: List[str],
    headers: Optional[Dict[str, str]] = None,
    referer: Optional[str] = None,
) -> Tuple[str, str]:
    if not urls:
        return "", ""
    if len(urls) == 1:
        text, final_url = await fetch_text(urls[0], headers=headers, referer=referer)
        return text, final_url

    client = await get_client()
    h = dict(headers or {})
    if referer:
        h["Referer"] = referer

    tasks: List[asyncio.Task] = []
    for u in urls:
        tasks.append(asyncio.create_task(client.get(u, headers=h, timeout=READ_TIMEOUT)))

    pending = set(tasks)
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            try:
                resp = task.result()
                if resp.status_code == 200 and len(resp.text) > 200 and not is_landing_page(resp.text):
                    winner_text = resp.text
                    winner_url = str(resp.url)
                    for p in pending:
                        p.cancel()
                    return winner_text, winner_url
            except Exception:
                pass

    return "", ""


async def fetch_text(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    referer: Optional[str] = None,
) -> Tuple[str, str]:
    """Fetch URL text with automatic retry and error handling."""
    client = await get_client()
    h = dict(headers or {})
    if referer:
        h["Referer"] = referer

    for attempt in range(REQUEST_RETRIES + 1):
        try:
            resp = await client.get(url, headers=h)
            if resp.status_code == 200:
                return resp.text, str(resp.url)
            if resp.status_code in (301, 302, 307, 308):
                loc = resp.headers.get("Location")
                if loc:
                    return await fetch_text(urllib.parse.urljoin(url, loc), headers=h)
        except httpx.RequestError as e:
            if attempt >= REQUEST_RETRIES:
                logger.debug(f"Failed to fetch {url}: {e}")
                break
            await asyncio.sleep(0.3 * (attempt + 1))
        except Exception as e:
            logger.debug(f"Unexpected error fetching {url}: {e}")
            break
    return "", ""


async def fetch_json(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    referer: Optional[str] = None,
) -> Any:
    text, _ = await fetch_text(url, headers=headers, referer=referer)
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


# Initialize cache at load time
restore_cache_from_disk()
