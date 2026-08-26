"""
Performance and resilience helpers for the MoviesDrive addon.

Everything in here used to be re-created on every single scrape step inside
moviesdrive_router.py. Centralising it removes most of the latency, and it is
also the single place where "MoviesDrive returned nothing" can be diagnosed:

* one shared httpx.AsyncClient (keep-alive + HTTP/2) instead of a brand new
  client - and therefore a brand new TLS handshake - per request
* split connect/read timeouts so a dead mirror fails in ~3s instead of ~12s
* the MoviesDrive domains are configuration, not code: MD_BASE_URL, MD_MIRRORS
  and MD_MIRROR_TEMPLATES are merged with whatever the callers register, probed
  concurrently, and the winner is pinned while failing mirrors go on cooldown
* anti-bot awareness: a Cloudflare / DDoS-Guard interstitial answers with HTTP
  200 and a body, so it used to win the mirror race and pin a broken mirror for
  the whole process. Such a body is now rejected, and can optionally be fetched
  for real through curl_cffi impersonation or FlareSolverr.
* every non-200 answer and every block is logged with its status code, so an
  empty catalog can be traced to a dead domain / a 403 challenge / a changed
  selector instead of failing silently
* a TTL cache with LRU eviction, negative caching, single-flight de-duplication,
  stale-while-revalidate and JSON persistence to disk, so a restart does not
  cold-start every lookup again
* lxml-based HTML parsing, falling back to html.parser when lxml is missing
"""

import asyncio
import base64
import json
import logging
import os
import re
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


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return bool(default)
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _env_list(name: str) -> List[str]:
    raw = os.getenv(name) or ""
    return [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()]


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

# Domain / anti-bot knobs
MD_PORTAL_URL = (os.getenv("MD_PORTAL_URL") or "https://moviesdrives.cfd").strip()
MIRROR_RANGE_RAW = os.getenv("MD_MIRROR_RANGE") or "1-6"
BASE_PROBE_PATH = os.getenv("MD_BASE_PROBE_PATH") or "/"
BASE_PROBE_TIMEOUT = _env_float("MD_BASE_PROBE_TIMEOUT", 6.0)
BASE_DISCOVERY_TTL = _env_float("MD_BASE_DISCOVERY_TTL", 900.0)
BASE_COOLDOWN = _env_float("MD_BASE_COOLDOWN", 300.0)
BASE_MAX_FAILURES = _env_int("MD_BASE_MAX_FAILURES", 3)
MAX_RACE_MIRRORS = _env_int("MD_MAX_RACE_MIRRORS", 4)
MAX_DISCOVERY_PROBES = _env_int("MD_MAX_DISCOVERY_PROBES", 12)
MIN_HTML_LENGTH = _env_int("MD_MIN_HTML_LENGTH", 400)
ANTIBOT_FALLBACK = _env_bool("MD_ANTIBOT_FALLBACK", True)
IMPERSONATE = os.getenv("MD_IMPERSONATE") or "chrome120"
FLARESOLVERR_URL = (os.getenv("MD_FLARESOLVERR_URL") or "").strip()
FLARESOLVERR_TIMEOUT = _env_float("MD_FLARESOLVERR_TIMEOUT", 40.0)

DEFAULT_BLOCK_MARKERS = (
    "just a moment",
    "checking your browser",
    "attention required! | cloudflare",
    "cf-browser-verification",
    "cf_chl_opt",
    "__cf_chl_",
    "ddos-guard",
    "enable javascript and cookies to continue",
    "please turn javascript on",
)
BLOCK_MARKERS = tuple(
    marker.lower()
    for marker in (list(DEFAULT_BLOCK_MARKERS) + _env_list("MD_BLOCK_MARKERS"))
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
}

try:  # optional: TLS fingerprint impersonation for challenged pages
    from curl_cffi import requests as curl_requests  # type: ignore

    _HAS_CURL_CFFI = True
except Exception:  # pragma: no cover - curl_cffi is optional
    curl_requests = None  # type: ignore
    _HAS_CURL_CFFI = False


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
# Anti-bot detection
# ------------------------------------------------------------------
def looks_blocked(text: str) -> bool:
    """True when a body is a bot challenge instead of real content.

    Cloudflare and DDoS-Guard answer with HTTP 200 plus a small HTML page, so
    the status code alone cannot be trusted.
    """
    if not text:
        return False
    sample = text[:4000].lower()
    return any(marker in sample for marker in BLOCK_MARKERS)


def content_ok(text: str, *, min_length: Optional[int] = None) -> bool:
    """True when a body looks like a real page worth parsing."""
    if not text:
        return False
    if looks_blocked(text):
        return False
    return len(text) >= (MIN_HTML_LENGTH if min_length is None else int(min_length))


# ------------------------------------------------------------------
# Domain registry: env driven, probed, pinned, with cooldown
# ------------------------------------------------------------------
_KNOWN_BASES: List[str] = []
_BASE_FAILURES: Dict[str, int] = {}
_BASE_COOLDOWN_UNTIL: Dict[str, float] = {}
_ACTIVE_BASE: Optional[str] = None
_LAST_DISCOVERY = 0.0
_DISCOVERY_LOCK: Optional[asyncio.Lock] = None


def _norm_base(base: str) -> str:
    return (base or "").strip().rstrip("/")


def env_base() -> Optional[str]:
    """The MoviesDrive base URL from MD_BASE_URL, when configured."""
    raw = _norm_base(os.getenv("MD_BASE_URL") or "")
    return raw or None


def env_mirrors() -> List[str]:
    """Extra mirrors from MD_MIRRORS (comma separated)."""
    return [_norm_base(item) for item in _env_list("MD_MIRRORS") if _norm_base(item)]


def _mirror_range() -> Tuple[int, int]:
    raw = MIRROR_RANGE_RAW.strip()
    try:
        if "-" in raw:
            low_raw, high_raw = raw.split("-", 1)
            low, high = int(low_raw), int(high_raw)
        else:
            low = high = int(raw)
    except (TypeError, ValueError):
        low, high = 1, 6
    if high < low:
        low, high = high, low
    return max(0, low), min(high, low + 19)


def generated_bases() -> List[str]:
    """Mirror guesses from MD_MIRROR_TEMPLATES, e.g. https://new{n}.example.tld"""
    templates = _env_list("MD_MIRROR_TEMPLATES")
    if not templates:
        return []
    low, high = _mirror_range()
    out: List[str] = []
    for template in templates:
        if "{n}" not in template:
            candidate = _norm_base(template)
            if candidate and candidate not in out:
                out.append(candidate)
            continue
        for number in range(low, high + 1):
            candidate = _norm_base(template.replace("{n}", str(number)))
            if candidate and candidate not in out:
                out.append(candidate)
    return out


def register_bases(*bases: Any) -> List[str]:
    """Register known MoviesDrive bases and return the full known list."""
    for base in bases:
        if isinstance(base, (list, tuple, set)):
            register_bases(*base)
            continue
        candidate = _norm_base(str(base or ""))
        if candidate and candidate not in _KNOWN_BASES:
            _KNOWN_BASES.append(candidate)
    return list(_KNOWN_BASES)


def known_bases() -> List[str]:
    return list(_KNOWN_BASES)


def base_is_cooling(base: str) -> bool:
    until = _BASE_COOLDOWN_UNTIL.get(_norm_base(base))
    return bool(until and until > time.time())


def note_base_failure(base: Optional[str], reason: str = "") -> None:
    candidate = _norm_base(base or "")
    if not candidate:
        return
    failures = _BASE_FAILURES.get(candidate, 0) + 1
    _BASE_FAILURES[candidate] = failures
    if failures >= BASE_MAX_FAILURES and not base_is_cooling(candidate):
        _BASE_COOLDOWN_UNTIL[candidate] = time.time() + BASE_COOLDOWN
        logger.warning(
            "MoviesDrive mirror %s put on cooldown for %.0fs after %s failures (%s)",
            candidate,
            BASE_COOLDOWN,
            failures,
            reason or "no usable response",
        )
        global _ACTIVE_BASE
        if _ACTIVE_BASE == candidate:
            _ACTIVE_BASE = None


def note_base_success(base: Optional[str]) -> None:
    candidate = _norm_base(base or "")
    if not candidate:
        return
    _BASE_FAILURES.pop(candidate, None)
    _BASE_COOLDOWN_UNTIL.pop(candidate, None)


def get_active_base(default: str) -> str:
    """The base every caller should build URLs on right now.

    Priority: the pinned mirror, then MD_BASE_URL, then the caller default.
    """
    if _ACTIVE_BASE and not base_is_cooling(_ACTIVE_BASE):
        return _ACTIVE_BASE
    configured = env_base()
    if configured and not base_is_cooling(configured):
        return configured
    return _norm_base(default) or default


def note_active_base(base: str) -> None:
    global _ACTIVE_BASE
    candidate = _norm_base(base)
    if candidate and candidate != _ACTIVE_BASE:
        _ACTIVE_BASE = candidate
        register_bases(candidate)
        logger.info("MoviesDrive mirror pinned to %s", candidate)
    note_base_success(candidate)


def active_base() -> Optional[str]:
    return _ACTIVE_BASE


def candidate_bases(
    default: Optional[str] = None,
    *,
    extra: Iterable[str] = (),
    include_generated: Optional[bool] = None,
    limit: Optional[int] = None,
) -> List[str]:
    """Ordered mirror candidates: pinned, env, registered, then guesses."""
    ordered: List[str] = []

    def _add(base: Optional[str]) -> None:
        candidate = _norm_base(base or "")
        if candidate and candidate not in ordered:
            ordered.append(candidate)

    _add(_ACTIVE_BASE)
    _add(env_base())
    for base in env_mirrors():
        _add(base)
    for base in extra:
        _add(base)
    for base in _KNOWN_BASES:
        _add(base)
    _add(default)

    healthy = [base for base in ordered if not base_is_cooling(base)]
    if include_generated is None:
        include_generated = not healthy
    if include_generated:
        for base in generated_bases():
            candidate = _norm_base(base)
            if candidate and candidate not in healthy and not base_is_cooling(candidate):
                healthy.append(candidate)

    result = healthy or ordered
    if limit is not None and limit > 0:
        result = result[:limit]
    return result


def base_of(url: str, bases: Iterable[str]) -> Optional[str]:
    for base in bases:
        if base and url.startswith(base):
            return base
    return None


def path_of(url: str, bases: Iterable[str] = ()) -> Optional[str]:
    """Strip any known base from a URL, returning the path (or None)."""
    for base in list(bases) + _KNOWN_BASES:
        candidate = _norm_base(base or "")
        if candidate and url.startswith(candidate):
            path = url[len(candidate):]
            return path if path.startswith("/") else "/" + path
    return None


def rebase(url: str, base: str, bases: Iterable[str] = ()) -> str:
    """Move a URL onto another mirror, keeping its path."""
    path = path_of(url, bases)
    if path is None:
        return url
    return _norm_base(base) + path


def mirror_candidates(url: str, bases: Iterable[str], primary: str) -> List[str]:
    """Rewrite a URL onto every usable mirror, preferring the pinned one."""
    base_list = [_norm_base(base) for base in bases if _norm_base(base)]
    register_bases(*(base_list + [primary]))
    path = path_of(url, base_list + [primary])
    if path is None:
        return [url]

    ordered: List[str] = []
    for base in candidate_bases(primary, extra=base_list, limit=MAX_RACE_MIRRORS):
        candidate = base + path
        if candidate not in ordered:
            ordered.append(candidate)
    if not ordered:
        ordered.append(url)
    return ordered


# ------------------------------------------------------------------
# Shared HTTP client
# ------------------------------------------------------------------
_CLIENT: Optional[httpx.AsyncClient] = None
_CLIENT_LOCK: Optional[asyncio.Lock] = None
_CLIENT_LOOP: Optional[asyncio.AbstractEventLoop] = None
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
    global _CLIENT, _CLIENT_LOOP
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _CLIENT is not None and not _CLIENT.is_closed and _CLIENT_LOOP is current_loop:
        return _CLIENT
    async with _client_lock():
        if _CLIENT is None or _CLIENT.is_closed or _CLIENT_LOOP is not current_loop:
            if _CLIENT is not None and not _CLIENT.is_closed:
                try:
                    await _CLIENT.aclose()
                except Exception:
                    pass
            _CLIENT = _build_client()
            _CLIENT_LOOP = current_loop
    return _CLIENT


async def aclose_client() -> None:
    global _CLIENT, _CLIENT_LOOP
    client = _CLIENT
    _CLIENT = None
    _CLIENT_LOOP = None
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
BLOCK_STATUS = (401, 403, 406, 429, 503)


async def fetch_response(
    url: str,
    *,
    referer: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    retries: int = REQUEST_RETRIES,
    read_timeout: Optional[float] = None,
) -> Optional[httpx.Response]:
    """GET a URL on the shared client. Returns None when it never succeeded.

    Unlike the previous version, every non-200 answer is logged with its status
    code and counted against the mirror it came from.
    """
    client = await get_client()
    req_headers = dict(headers) if headers else {}
    if referer:
        req_headers["Referer"] = referer
    timeout = _timeout_for(read_timeout)
    origin = base_of(url, _KNOWN_BASES)

    attempt = 0
    while True:
        try:
            if timeout is not None:
                resp = await client.get(url, headers=req_headers, timeout=timeout)
            else:
                resp = await client.get(url, headers=req_headers)
            if resp.status_code == 200:
                note_base_success(origin)
                return resp
            if resp.status_code in RETRY_STATUS and attempt < retries:
                attempt += 1
                logger.info(
                    "MoviesDrive HTTP %s for %s, retry %s/%s",
                    resp.status_code,
                    url,
                    attempt,
                    retries,
                )
                await asyncio.sleep(0.4 * attempt)
                continue
            logger.warning(
                "MoviesDrive HTTP %s for %s%s",
                resp.status_code,
                url,
                " (looks like a bot challenge)"
                if resp.status_code in BLOCK_STATUS
                else "",
            )
            note_base_failure(origin, "HTTP %s" % resp.status_code)
            return None
        except asyncio.CancelledError:
            raise
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if attempt < retries:
                attempt += 1
                await asyncio.sleep(0.4 * attempt)
                continue
            logger.warning("MoviesDrive request failed for %s: %s", url, exc)
            note_base_failure(origin, type(exc).__name__)
            return None
        except Exception as exc:
            logger.warning("MoviesDrive request error for %s: %s", url, exc)
            note_base_failure(origin, type(exc).__name__)
            return None


def _curl_get(url: str, headers: Dict[str, str], timeout: float):  # pragma: no cover
    return curl_requests.get(  # type: ignore[union-attr]
        url,
        headers=headers,
        impersonate=IMPERSONATE,
        timeout=timeout,
        allow_redirects=True,
    )


async def _fetch_via_curl_cffi(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    read_timeout: Optional[float] = None,
) -> Tuple[str, str]:
    """Retry a challenged page with a real browser TLS fingerprint."""
    if not _HAS_CURL_CFFI:
        return "", ""
    req_headers = dict(DEFAULT_HEADERS)
    if headers:
        req_headers.update(headers)
    timeout = float(read_timeout or READ_TIMEOUT)
    try:
        resp = await asyncio.to_thread(_curl_get, url, req_headers, timeout)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("MoviesDrive curl_cffi fallback failed for %s: %s", url, exc)
        return "", ""
    status = getattr(resp, "status_code", 0)
    if status != 200:
        logger.warning("MoviesDrive curl_cffi HTTP %s for %s", status, url)
        return "", ""
    try:
        text = resp.text or ""
    except Exception:
        return "", ""
    if looks_blocked(text):
        logger.warning("MoviesDrive curl_cffi still blocked for %s", url)
        return "", ""
    logger.info("MoviesDrive curl_cffi fallback solved %s", url)
    return text, str(getattr(resp, "url", url) or url)


async def _fetch_via_flaresolverr(url: str) -> Tuple[str, str]:
    """Ask a FlareSolverr instance to solve the challenge, when configured."""
    if not FLARESOLVERR_URL:
        return "", ""
    payload = {
        "cmd": "request.get",
        "url": url,
        "maxTimeout": int(FLARESOLVERR_TIMEOUT * 1000),
    }
    try:
        client = await get_client()
        resp = await client.post(
            FLARESOLVERR_URL,
            json=payload,
            timeout=httpx.Timeout(
                connect=CONNECT_TIMEOUT,
                read=FLARESOLVERR_TIMEOUT + 5,
                write=FLARESOLVERR_TIMEOUT + 5,
                pool=POOL_TIMEOUT,
            ),
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("MoviesDrive FlareSolverr call failed for %s: %s", url, exc)
        return "", ""
    if resp.status_code != 200:
        logger.warning("MoviesDrive FlareSolverr HTTP %s for %s", resp.status_code, url)
        return "", ""
    try:
        solution = (resp.json() or {}).get("solution") or {}
    except Exception as exc:
        logger.warning("MoviesDrive FlareSolverr decode failed for %s: %s", url, exc)
        return "", ""
    text = solution.get("response") or ""
    if not text or looks_blocked(text):
        logger.warning("MoviesDrive FlareSolverr could not solve %s", url)
        return "", ""
    logger.info("MoviesDrive FlareSolverr solved %s", url)
    return text, str(solution.get("url") or url)


def antibot_available() -> bool:
    return ANTIBOT_FALLBACK and (_HAS_CURL_CFFI or bool(FLARESOLVERR_URL))


async def fetch_antibot(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    read_timeout: Optional[float] = None,
) -> Tuple[str, str]:
    """Try every configured anti-bot bypass for a single URL."""
    if not antibot_available():
        return "", ""
    text, final_url = await _fetch_via_curl_cffi(
        url, headers=headers, read_timeout=read_timeout
    )
    if text:
        return text, final_url
    return await _fetch_via_flaresolverr(url)


async def fetch_text(
    url: str,
    *,
    referer: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    retries: int = REQUEST_RETRIES,
    read_timeout: Optional[float] = None,
    allow_antibot: bool = True,
) -> Tuple[str, str]:
    """Return (body, final_url). Both are empty strings on failure.

    A bot-challenge body is treated as a failure so it can never be parsed as
    content nor win a mirror race.
    """
    resp = await fetch_response(
        url,
        referer=referer,
        headers=headers,
        retries=retries,
        read_timeout=read_timeout,
    )
    text = ""
    final_url = ""
    if resp is not None:
        try:
            text = resp.text or ""
            final_url = str(resp.url)
        except Exception:
            text = ""
            final_url = str(getattr(resp, "url", "") or "")

    blocked = looks_blocked(text)
    if text and not blocked:
        return text, final_url
    if blocked:
        logger.warning("MoviesDrive got an anti-bot challenge page for %s", url)
        note_base_failure(base_of(url, _KNOWN_BASES), "anti-bot challenge")

    if allow_antibot and (blocked or not text) and antibot_available():
        solved, solved_url = await fetch_antibot(
            url, headers=headers, read_timeout=read_timeout
        )
        if solved:
            return solved, solved_url or final_url or url

    return "", ""


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
        try:
            body = resp.text or ""
        except Exception:
            body = ""
        if looks_blocked(body):
            logger.warning(
                "MoviesDrive expected JSON but got an anti-bot challenge for %s", url
            )
        else:
            logger.warning(
                "MoviesDrive JSON decode failed for %s: %s (body starts with %r)",
                url,
                exc,
                body[:120],
            )
        return None


# ------------------------------------------------------------------
# Mirror probing / discovery
# ------------------------------------------------------------------
def _discovery_lock() -> asyncio.Lock:
    global _DISCOVERY_LOCK
    if _DISCOVERY_LOCK is None:
        _DISCOVERY_LOCK = asyncio.Lock()
    return _DISCOVERY_LOCK


async def fetch_portal_mirrors(portal_url: Optional[str] = None) -> List[str]:
    """Fetch the latest active MoviesDrive domains from the official portal page (e.g. moviesdrives.cfd)."""
    target = (portal_url or MD_PORTAL_URL or "").strip()
    if not target:
        return []

    logger.info("MoviesDrive querying portal for latest active domains: %s", target)
    html, _ = await fetch_text(
        target,
        headers=dict(DEFAULT_HEADERS),
        retries=1,
        read_timeout=8.0,
        allow_antibot=False,
    )
    if not html:
        return []

    discovered: List[str] = []

    def _add(u: str) -> None:
        c = _norm_base(u)
        if c and ("moviesdrive" in c.lower() or "moviedrive" in c.lower()):
            if not c.endswith(".cfd") and c not in discovered:
                discovered.append(c)

    # 1. Decode base64 in atob(...) calls
    for b64 in re.findall(r'atob\(["\']([A-Za-z0-9+/=]+)["\']\)', html):
        try:
            decoded = base64.b64decode(b64).decode("utf-8", errors="ignore")
            for u in re.findall(r'https?://[a-zA-Z0-9.-]+', decoded):
                _add(u)
        except Exception:
            pass

    # 2. Decode base64 in script tags
    for script in re.findall(r'<script[^>]*>(.*?)</script>', html, flags=re.DOTALL):
        for b64 in re.findall(r'["\']([A-Za-z0-9+/=]{16,})["\']', script):
            try:
                decoded = base64.b64decode(b64).decode("utf-8", errors="ignore")
                for u in re.findall(r'https?://[a-zA-Z0-9.-]+', decoded):
                    _add(u)
            except Exception:
                pass

    # 3. Direct regex matches for domain patterns
    for u in re.findall(r'https?://[a-zA-Z0-9.-]*moviesdrive[a-zA-Z0-9.-]*', html, flags=re.IGNORECASE):
        _add(u)
    for u in re.findall(r'https?://[a-zA-Z0-9.-]*moviedrive[a-zA-Z0-9.-]*', html, flags=re.IGNORECASE):
        _add(u)

    if discovered:
        logger.info("MoviesDrive portal discovery found domains: %s", discovered)
        register_bases(*discovered)

    return discovered


async def probe_base(base: str) -> bool:
    """True when a mirror answers with real content (not a challenge page)."""
    candidate = _norm_base(base)
    if not candidate:
        return False
    url = candidate + (BASE_PROBE_PATH if BASE_PROBE_PATH.startswith("/") else "/" + BASE_PROBE_PATH)
    text, _ = await fetch_text(
        url,
        headers=dict(DEFAULT_HEADERS),
        retries=0,
        read_timeout=BASE_PROBE_TIMEOUT,
        allow_antibot=False,
    )
    return content_ok(text)


async def discover_active_base(
    default: Optional[str] = None,
    *,
    force: bool = False,
) -> Optional[str]:
    """Probe the mirror candidates concurrently and pin the first live one."""
    global _LAST_DISCOVERY
    now = time.time()
    if (
        not force
        and _ACTIVE_BASE
        and not base_is_cooling(_ACTIVE_BASE)
        and now - _LAST_DISCOVERY < BASE_DISCOVERY_TTL
    ):
        return _ACTIVE_BASE

    async with _discovery_lock():
        now = time.time()
        if (
            not force
            and _ACTIVE_BASE
            and not base_is_cooling(_ACTIVE_BASE)
            and now - _LAST_DISCOVERY < BASE_DISCOVERY_TTL
        ):
            return _ACTIVE_BASE

        # Query the portal to refresh domain candidates if forcing or unpinned
        if force or not _ACTIVE_BASE or base_is_cooling(_ACTIVE_BASE or ""):
            try:
                await fetch_portal_mirrors()
            except Exception as e:
                logger.warning("MoviesDrive portal discovery failed: %s", e)

        candidates = candidate_bases(
            default, include_generated=True, limit=MAX_DISCOVERY_PROBES
        )
        if not candidates:
            return _ACTIVE_BASE
        _LAST_DISCOVERY = now

        tasks: Dict["asyncio.Task[bool]", str] = {}
        for base in candidates:
            tasks[asyncio.ensure_future(probe_base(base))] = base

        winner: Optional[str] = None
        pending = set(tasks.keys())
        try:
            while pending and winner is None:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    base = tasks.get(task, "")
                    try:
                        alive = bool(task.result())
                    except Exception:
                        alive = False
                    if alive:
                        winner = base
                        break
                    note_base_failure(base, "probe failed")
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()

        if winner:
            note_active_base(winner)
            return winner

        # If all candidates failed, try fetching and probing portal mirrors directly
        try:
            portal_bases = await fetch_portal_mirrors()
            for base in portal_bases:
                if await probe_base(base):
                    note_active_base(base)
                    return base
        except Exception as exc:
            logger.warning("MoviesDrive fallback portal probe error: %s", exc)

        logger.warning(
            "MoviesDrive: none of the %s mirror candidates answered, set MD_BASE_URL "
            "or MD_MIRRORS to the current domain",
            len(candidates),
        )
        return _ACTIVE_BASE


async def race_fetch_text(
    urls: List[str],
    *,
    referer: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    read_timeout: Optional[float] = None,
    validator: Optional[Callable[[str], bool]] = None,
    allow_antibot: bool = True,
) -> Tuple[str, str]:
    """Fire every mirror at once and keep the first usable answer.

    A body that fails ``validator`` (default: any non-empty, non-challenge body)
    is discarded, so a Cloudflare interstitial can no longer be pinned as the
    active mirror.
    """
    if not urls:
        return "", ""

    check = validator or (lambda text: bool(text))

    async def _finish(text: str, final_url: str, fallback_url: str) -> Tuple[str, str]:
        resolved = final_url or fallback_url
        winner = base_of(resolved, _KNOWN_BASES)
        if winner:
            note_active_base(winner)
        return text, resolved

    if len(urls) == 1:
        text, final_url = await fetch_text(
            urls[0],
            referer=referer,
            headers=headers,
            read_timeout=read_timeout,
            allow_antibot=allow_antibot,
        )
        if text and check(text):
            return await _finish(text, final_url, urls[0])
        return "", ""

    tasks: Dict["asyncio.Task[Tuple[str, str]]", str] = {}
    for url in urls:
        task = asyncio.ensure_future(
            fetch_text(
                url,
                referer=referer,
                headers=headers,
                read_timeout=read_timeout,
                allow_antibot=False,
            )
        )
        tasks[task] = url

    pending = set(tasks.keys())
    try:
        while pending:
            done, pending = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                source = tasks.get(task, "")
                try:
                    text, final_url = task.result()
                except Exception:
                    continue
                if not text:
                    continue
                if not check(text):
                    logger.info(
                        "MoviesDrive discarded an unusable body from %s (%s bytes)",
                        source,
                        len(text),
                    )
                    note_base_failure(base_of(source, _KNOWN_BASES), "unusable body")
                    continue
                return await _finish(text, final_url, source)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

    if allow_antibot and antibot_available():
        for url in urls[:2]:
            text, final_url = await fetch_antibot(
                url, headers=headers, read_timeout=read_timeout
            )
            if text and check(text):
                return await _finish(text, final_url, url)

    logger.warning("MoviesDrive: every mirror failed for %s", urls[0])
    return "", ""


# ------------------------------------------------------------------
# TTL cache with LRU eviction and disk persistence
# ------------------------------------------------------------------
CACHE: "OrderedDict[str, Tuple[Any, float, float]]" = OrderedDict()
_CACHE_DIRTY = False
_CACHE_LAST_SAVE = 0.0


def get_cached(key: str) -> Optional[Any]:
    """Return cached data, or None when it is missing or expired.

    This used to be defined twice; the second definition ignored the TTL and
    happily returned expired - including negatively cached empty - values for
    the rest of the process lifetime.
    """
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
        "active_base": _ACTIVE_BASE,
        "env_base": env_base(),
        "known_bases": known_bases(),
        "cooling_bases": {
            base: round(until - now, 1)
            for base, until in _BASE_COOLDOWN_UNTIL.items()
            if until > now
        },
        "base_failures": dict(_BASE_FAILURES),
        "antibot": {
            "enabled": ANTIBOT_FALLBACK,
            "curl_cffi": _HAS_CURL_CFFI,
            "flaresolverr": bool(FLARESOLVERR_URL),
        },
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


# Whatever is configured in the environment is a known mirror from the start.
register_bases(env_base(), *env_mirrors())

# Restore whatever survived the last run as soon as the module is imported.
load_cache()
