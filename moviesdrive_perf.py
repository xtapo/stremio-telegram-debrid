"""
Performance helpers for the MoviesDrive addon.

Everything in here used to be re-created on every single scrape step inside
moviesdrive_router.py. Centralising it removes most of the latency:

* one shared httpx.AsyncClient (keep-alive + HTTP/2) instead of a brand new
  client - and therefore a brand new TLS handshake - per request
* split connect/read timeouts so a dead mirror fails in ~3s instead of ~12s
* mirror racing across the MoviesDrive domains, with the winner pinned
* a TTL cache with LRU eviction, negative caching, single-flight de-duplication,
  stale-while-revalidate and JSON persistence to disk, so a restart does not
  cold-start every lookup again
* lxml-based HTML parsing, falling back to html.parser when lxml is missing
"""

import asyncio
import json
import logging
import os
import tempfile
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup, SoupStrainer

try:  # the MD_* knobs below are read at import time, so .env must be loaded
    from dotenv import load_dotenv  # noqa: E402

    load_dotenv()
except Exception:  # pragma: no cover - python-dotenv is optional
    pass

logger = logging.getLogger("moviesdrive_addon")


# ------------------------------------------------------------------
# Tunables (all overridable from .env)
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


CONNECT_TIMEOUT = _env_float("MD_CONNECT_TIMEOUT", 3.0)
READ_TIMEOUT = _env_float("MD_READ_TIMEOUT", 12.0)
POOL_TIMEOUT = _env_float("MD_POOL_TIMEOUT", 5.0)
MAX_CONNECTIONS = _env_int("MD_MAX_CONNECTIONS", 40)
MAX_KEEPALIVE = _env_int("MD_MAX_KEEPALIVE", 20)
KEEPALIVE_EXPIRY = _env_float("MD_KEEPALIVE_EXPIRY", 90.0)
REQUEST_RETRIES = _env_int("MD_REQUEST_RETRIES", 1)

CACHE_TTL = _env_int("MD_CACHE_TTL", 300)
NEGATIVE_TTL = _env_int("MD_NEGATIVE_TTL", 60)
STREAM_CACHE_TTL = _env_int("MD_STREAM_CACHE_TTL", 1800)
CACHE_MAX_ENTRIES = _env_int("MD_CACHE_MAX_ENTRIES", 2000)
CACHE_SAVE_INTERVAL = _env_float("MD_CACHE_SAVE_INTERVAL", 15.0)
CACHE_PERSIST_MIN_TTL = _env_int("MD_CACHE_PERSIST_MIN_TTL", 600)
CACHE_FILE = os.getenv("MD_CACHE_FILE") or os.path.join(
    tempfile.gettempdir(), "moviesdrive_cache.json"
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
# HTML parsing
# ------------------------------------------------------------------
try:  # lxml is 3-5x faster than the pure-python parser on MoviesDrive posts
    import lxml  # noqa: F401

    HTML_PARSER = "lxml"
except Exception:  # pragma: no cover - depends on the deployment image
    HTML_PARSER = "html.parser"


def make_soup(markup: str, only: Optional[SoupStrainer] = None) -> BeautifulSoup:
    """Parse HTML with the fastest available parser."""
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
# Shared HTTP client
# ------------------------------------------------------------------
_CLIENT: Optional[httpx.AsyncClient] = None
_CLIENT_LOCK: Optional[asyncio.Lock] = None
_HTTP2_ENABLED = True


def _client_lock() -> asyncio.Lock:
    global _CLIENT_LOCK
    if _CLIENT_LOCK is None:
        _CLIENT_LOCK = asyncio.Lock()
    return _CLIENT_LOCK


def _build_client() -> httpx.AsyncClient:
    global _HTTP2_ENABLED
    limits = httpx.Limits(
        max_connections=MAX_CONNECTIONS,
        max_keepalive_connections=MAX_KEEPALIVE,
        keepalive_expiry=KEEPALIVE_EXPIRY,
    )
    timeout = httpx.Timeout(
        connect=CONNECT_TIMEOUT,
        read=READ_TIMEOUT,
        write=READ_TIMEOUT,
        pool=POOL_TIMEOUT,
    )
    kwargs: Dict[str, Any] = {
        "limits": limits,
        "timeout": timeout,
        "follow_redirects": True,
        "headers": dict(DEFAULT_HEADERS),
    }
    if _HTTP2_ENABLED:
        try:
            return httpx.AsyncClient(http2=True, **kwargs)
        except ImportError:
            _HTTP2_ENABLED = False
            logger.info("h2 is not installed, MoviesDrive falls back to HTTP/1.1 keep-alive")
    return httpx.AsyncClient(**kwargs)


async def get_client() -> httpx.AsyncClient:
    """Return the process-wide client, creating it on first use."""
    global _CLIENT
    if _CLIENT is not None and not _CLIENT.is_closed:
        return _CLIENT
    async with _client_lock():
        if _CLIENT is None or _CLIENT.is_closed:
            _CLIENT = _build_client()
    return _CLIENT


async def aclose_client() -> None:
    global _CLIENT
    client = _CLIENT
    _CLIENT = None
    if client is not None and not client.is_closed:
        try:
            await client.aclose()
        except Exception:
            pass


def _timeout_for(read_timeout: Optional[float]) -> Optional[httpx.Timeout]:
    if read_timeout is None:
        return None
    return httpx.Timeout(
        connect=CONNECT_TIMEOUT,
        read=read_timeout,
        write=read_timeout,
        pool=POOL_TIMEOUT,
    )


RETRY_STATUS = (429, 500, 502, 503, 504)


async def fetch_response(
    url: str,
    *,
    referer: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    retries: int = REQUEST_RETRIES,
    read_timeout: Optional[float] = None,
) -> Optional[httpx.Response]:
    """GET a URL on the shared client. Returns None when it never succeeded."""
    client = await get_client()
    req_headers = dict(headers) if headers else {}
    if referer:
        req_headers["Referer"] = referer
    timeout = _timeout_for(read_timeout)

    attempt = 0
    while True:
        try:
            if timeout is not None:
                resp = await client.get(url, headers=req_headers, timeout=timeout)
            else:
                resp = await client.get(url, headers=req_headers)
            if resp.status_code == 200:
                return resp
            if resp.status_code in RETRY_STATUS and attempt < retries:
                attempt += 1
                await asyncio.sleep(0.4 * attempt)
                continue
            return None
        except asyncio.CancelledError:
            raise
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if attempt < retries:
                attempt += 1
                await asyncio.sleep(0.4 * attempt)
                continue
            logger.warning("MoviesDrive request failed for %s: %s", url, exc)
            return None
        except Exception as exc:
            logger.warning("MoviesDrive request error for %s: %s", url, exc)
            return None


async def fetch_text(
    url: str,
    *,
    referer: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    retries: int = REQUEST_RETRIES,
    read_timeout: Optional[float] = None,
) -> Tuple[str, str]:
    """Return (body, final_url). Both are empty strings on failure."""
    resp = await fetch_response(
        url,
        referer=referer,
        headers=headers,
        retries=retries,
        read_timeout=read_timeout,
    )
    if resp is None:
        return "", ""
    try:
        return resp.text, str(resp.url)
    except Exception:
        return "", str(getattr(resp, "url", "") or "")


async def fetch_json(
    url: str,
    *,
    referer: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    retries: int = REQUEST_RETRIES,
    read_timeout: Optional[float] = None,
) -> Optional[Any]:
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    resp = await fetch_response(
        url,
        referer=referer,
        headers=req_headers,
        retries=retries,
        read_timeout=read_timeout,
    )
    if resp is None:
        return None
    try:
        return resp.json()
    except Exception as exc:
        logger.warning("MoviesDrive JSON decode failed for %s: %s", url, exc)
        return None


# ------------------------------------------------------------------
# TTL cache with LRU eviction and disk persistence
# ------------------------------------------------------------------
CACHE: "OrderedDict[str, Tuple[Any, float, float]]" = OrderedDict()
_CACHE_DIRTY = False
_CACHE_LAST_SAVE = 0.0


def get_cached(key: str) -> Optional[Any]:
    entry = CACHE.get(key)
    if entry is None:
        return None
    data, ts, ttl = entry
    if time.time() - ts >= ttl:
        CACHE.pop(key, None)
        return None
    CACHE.move_to_end(key)
    return data


def get_entry(key: str) -> Optional[Tuple[Any, float, float]]:
    """Return (data, age_seconds, ttl) even when the entry is already stale."""
    entry = CACHE.get(key)
    if entry is None:
        return None
    data, ts, ttl = entry
    return data, time.time() - ts, ttl


def get_cached(key: str) -> Optional[Any]:
    """Return cached data or None."""
    entry = CACHE.get(key)
    return entry[0] if entry else None


def set_cached(key: str, data: Any, ttl: float = CACHE_TTL) -> None:
    global _CACHE_DIRTY
    CACHE[key] = (data, time.time(), float(ttl))
    CACHE.move_to_end(key)
    _CACHE_DIRTY = True
    if len(CACHE) > CACHE_MAX_ENTRIES:
        _evict()


def invalidate(key: str) -> None:
    CACHE.pop(key, None)


def _evict() -> None:
    """Drop expired entries first, then the least recently used ones.

    The old implementation called CACHE.clear(), which also threw away the
    expensive 30-minute resolved-stream entries.
    """
    now = time.time()
    for key in [k for k, (_, ts, ttl) in list(CACHE.items()) if now - ts >= ttl]:
        CACHE.pop(key, None)
    target = max(1, int(CACHE_MAX_ENTRIES * 0.9))
    while len(CACHE) > target:
        CACHE.popitem(last=False)


def _is_serialisable(value: Any) -> bool:
    try:
        json.dumps(value)
        return True
    except (TypeError, ValueError):
        return False


def save_cache(force: bool = False) -> None:
    """Persist long-lived entries so a restart does not cold-start everything."""
    global _CACHE_DIRTY, _CACHE_LAST_SAVE
    now = time.time()
    if not force:
        if not _CACHE_DIRTY or now - _CACHE_LAST_SAVE < CACHE_SAVE_INTERVAL:
            return
    payload: Dict[str, Any] = {}
    for key, (data, ts, ttl) in list(CACHE.items()):
        if ttl < CACHE_PERSIST_MIN_TTL or now - ts >= ttl:
            continue
        if not _is_serialisable(data):
            continue
        payload[key] = {"data": data, "ts": ts, "ttl": ttl}
    tmp_path = CACHE_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(tmp_path, CACHE_FILE)
        _CACHE_DIRTY = False
        _CACHE_LAST_SAVE = now
    except Exception as exc:
        logger.warning("Could not persist the MoviesDrive cache: %s", exc)


def load_cache() -> int:
    """Restore the persisted cache. Returns how many entries were restored."""
    if not os.path.exists(CACHE_FILE):
        return 0
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        logger.warning("Could not read the MoviesDrive cache file: %s", exc)
        return 0
    if not isinstance(payload, dict):
        return 0
    now = time.time()
    restored = 0
    for key, item in payload.items():
        if not isinstance(item, dict):
            continue
        ts = float(item.get("ts") or 0)
        ttl = float(item.get("ttl") or 0)
        if ttl <= 0 or now - ts >= ttl:
            continue
        CACHE[key] = (item.get("data"), ts, ttl)
        restored += 1
    if restored:
        logger.info("Restored %s MoviesDrive cache entries from disk", restored)
    return restored


async def cache_autosave_loop(interval: Optional[float] = None) -> None:
    period = float(interval or CACHE_SAVE_INTERVAL)
    while True:
        try:
            await asyncio.sleep(period)
            save_cache()
        except asyncio.CancelledError:
            save_cache(force=True)
            raise
        except Exception as exc:
            logger.warning("MoviesDrive cache autosave error: %s", exc)


def cache_stats() -> Dict[str, Any]:
    now = time.time()
    fresh = sum(1 for _, ts, ttl in CACHE.values() if now - ts < ttl)
    return {
        "entries": len(CACHE),
        "fresh": fresh,
        "stale": len(CACHE) - fresh,
        "file": CACHE_FILE,
        "parser": HTML_PARSER,
        "http2": _HTTP2_ENABLED,
    }


# ------------------------------------------------------------------
# Single flight + stale-while-revalidate
# ------------------------------------------------------------------
_INFLIGHT: Dict[str, "asyncio.Task[Any]"] = {}


def _is_empty(value: Any) -> bool:
    return value is None or value == [] or value == {} or value == ""


async def _produce(
    key: str,
    factory: Callable[[], Any],
    ttl: float,
    negative_ttl: float,
) -> Any:
    try:
        value = factory()
        if asyncio.iscoroutine(value) or isinstance(value, asyncio.Future):
            value = await value
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("MoviesDrive lookup failed for %s: %s", key, exc)
        value = None
    if _is_empty(value):
        if negative_ttl > 0:
            set_cached(key, value, negative_ttl)
    else:
        set_cached(key, value, ttl)
    return value


def _spawn(key: str, factory: Callable[[], Any], ttl: float, negative_ttl: float):
    task = _INFLIGHT.get(key)
    if task is not None and not task.done():
        return task
    task = asyncio.ensure_future(_produce(key, factory, ttl, negative_ttl))
    _INFLIGHT[key] = task
    task.add_done_callback(lambda done, k=key: _INFLIGHT.pop(k, None))
    return task


async def cached_call(
    key: str,
    factory: Callable[[], Any],
    *,
    ttl: float = CACHE_TTL,
    negative_ttl: float = NEGATIVE_TTL,
    stale_ttl: float = 0.0,
    force: bool = False,
) -> Any:
    """Cache an async lookup.

    * concurrent callers for the same key share one upstream request
    * empty results are negatively cached for a short while
    * with stale_ttl > 0 an expired value is served immediately while it is
      refreshed in the background (stale-while-revalidate)
    """
    if not force:
        entry = get_entry(key)
        if entry is not None:
            data, age, ttl_stored = entry
            if age < ttl_stored:
                return data
            if stale_ttl > 0 and age < ttl_stored + stale_ttl and not _is_empty(data):
                _spawn(key, factory, ttl, negative_ttl)
                return data
            invalidate(key)
    return await asyncio.shield(_spawn(key, factory, ttl, negative_ttl))


# ------------------------------------------------------------------
# Mirror racing
# ------------------------------------------------------------------
_ACTIVE_BASE: Optional[str] = None


def get_active_base(default: str) -> str:
    return _ACTIVE_BASE or default


def note_active_base(base: str) -> None:
    global _ACTIVE_BASE
    if base and base != _ACTIVE_BASE:
        _ACTIVE_BASE = base
        logger.info("MoviesDrive mirror pinned to %s", base)


def mirror_candidates(url: str, bases: Iterable[str], primary: str) -> List[str]:
    """Rewrite a URL onto every known mirror, preferring the pinned one."""
    path = url
    for base in list(bases) + [primary]:
        if base and path.startswith(base):
            path = path[len(base):]
            break
    else:
        return [url]
    if not path.startswith("/"):
        path = "/" + path

    ordered: List[str] = []
    active = _ACTIVE_BASE
    for base in ([active] if active else []) + list(bases) + [primary]:
        if not base:
            continue
        candidate = base.rstrip("/") + path
        if candidate not in ordered:
            ordered.append(candidate)
    return ordered or [url]


def base_of(url: str, bases: Iterable[str]) -> Optional[str]:
    for base in bases:
        if base and url.startswith(base):
            return base
    return None


async def race_fetch_text(
    urls: List[str],
    *,
    referer: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    read_timeout: Optional[float] = None,
) -> Tuple[str, str]:
    """Fire every mirror at once and keep the first usable answer."""
    if not urls:
        return "", ""
    if len(urls) == 1:
        return await fetch_text(
            urls[0], referer=referer, headers=headers, read_timeout=read_timeout
        )

    tasks: Dict["asyncio.Task[Tuple[str, str]]", str] = {}
    for url in urls:
        task = asyncio.ensure_future(
            fetch_text(url, referer=referer, headers=headers, read_timeout=read_timeout)
        )
        tasks[task] = url

    pending = set(tasks.keys())
    try:
        while pending:
            done, pending = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                try:
                    text, final_url = task.result()
                except Exception:
                    continue
                if text:
                    return text, final_url or tasks.get(task, "")
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
    return "", ""


# ------------------------------------------------------------------
# Prewarming
# ------------------------------------------------------------------
async def run_prewarm(
    jobs: Iterable[Callable[[], Awaitable[Any]]],
    delay: float = 0.0,
    label: str = "MoviesDrive prewarm",
) -> None:
    if delay > 0:
        await asyncio.sleep(delay)
    started = time.time()
    results = await asyncio.gather(
        *[job() for job in jobs], return_exceptions=True
    )
    failed = sum(1 for item in results if isinstance(item, Exception))
    logger.info(
        "%s finished in %.1fs (%s jobs, %s failed)",
        label,
        time.time() - started,
        len(results),
        failed,
    )


def schedule_prewarm(
    jobs: Iterable[Callable[[], Awaitable[Any]]],
    delay: float = 2.0,
    label: str = "MoviesDrive prewarm",
):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    return loop.create_task(run_prewarm(jobs, delay=delay, label=label))


# Restore whatever survived the last run as soon as the module is imported.
load_cache()
