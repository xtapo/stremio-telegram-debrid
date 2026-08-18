"""
Link resolving layer for the MoviesDrive addon.

A MoviesDrive lookup is a four level chain:

    post page -> mdrive archive page -> hubcloud page -> gamerxyt page

The old code walked the whole chain for every quality before answering Stremio.
Here it is split in two halves:

* collect_candidates() only needs the post page (level 1) and is enough to build
  the stream list.
* resolve_playable_url() walks levels 2-4 and runs only for the stream the user
  actually pressed play on, or in the background to warm the cache.

Every step is cached, de-duplicated and negatively cached by moviesdrive_perf.

All hosts are configuration, not code: MD_BASE_URL / MD_MIRRORS (see
moviesdrive_perf), MD_HUBCLOUD_BASE and MD_GAMERXYT_BASE. When a source changes
domain nothing here has to be edited.
"""

import asyncio
import html as html_lib
import logging
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional

from bs4 import SoupStrainer

import moviesdrive_perf as perf
from moviesdrive_perf import (
    NEGATIVE_TTL,
    STREAM_CACHE_TTL,
    base_of,
    cached_call,
    content_ok,
    fetch_text,
    get_active_base,
    make_soup,
    mirror_candidates,
    race_fetch_text,
)

logger = logging.getLogger("moviesdrive_addon")

# The defaults are only a starting point - MD_BASE_URL / MD_MIRRORS win.
DEFAULT_BASE_URL = "https://new2.moviesdrive.christmas"
DEFAULT_BACKUP_URLS = [
    "https://new2.moviesdrive.christmas",
    "https://new1.moviesdrive.christmas",
    "https://moviesdrives.mov",
]

MOVIESDRIVE_BASE_URL = perf.env_base() or DEFAULT_BASE_URL
MOVIESDRIVE_BACKUP_URLS = list(
    dict.fromkeys(
        [url.rstrip("/") for url in (perf.env_mirrors() + DEFAULT_BACKUP_URLS)]
        + [MOVIESDRIVE_BASE_URL.rstrip("/")]
    )
)
# Registering them makes perf aware of every host it may see in a redirect.
ALL_BASES = perf.register_bases(*MOVIESDRIVE_BACKUP_URLS)

HUBCLOUD_BASE = (os.getenv("MD_HUBCLOUD_BASE") or "https://hubcloud.cx").rstrip("/")
HUBCLOUD_SEARCH_PATH = os.getenv("MD_HUBCLOUD_SEARCH_PATH") or "/drive/search-recover.php"
HUBCLOUD_SEARCH_ENDPOINT = HUBCLOUD_BASE + HUBCLOUD_SEARCH_PATH
GAMERXYT_BASE = (os.getenv("MD_GAMERXYT_BASE") or "https://gamerxyt.com").rstrip("/") + "/"
GAMERXYT_HOSTS = tuple(
    perf._env_list("MD_GAMERXYT_HOSTS")
    or [urllib.parse.urlsplit(GAMERXYT_BASE).netloc or "gamerxyt.com"]
)
FSL_HOSTS = tuple(perf._env_list("MD_FSL_HOSTS") or ["cloudflarestorage.com", "r2.dev"])
WORKER_HOSTS = tuple(perf._env_list("MD_WORKER_HOSTS") or ["workers.dev"])
EXTRA_DIRECT_HOSTS = tuple(perf._env_list("MD_DIRECT_HOSTS"))
MEDIA_EXTENSIONS = (".mkv", ".mp4", ".m4v", ".avi")

# Kept for backwards compatibility - callers that need a live Referer should use
# request_headers() instead, because the pinned mirror can change at runtime.
HEADERS = {
    "User-Agent": perf.USER_AGENT,
    "Referer": MOVIESDRIVE_BASE_URL + "/",
}

POST_TTL = perf._env_int("MD_POST_TTL", 900)
POST_STALE_TTL = perf._env_int("MD_POST_STALE_TTL", 3600)
ARCHIVE_TTL = perf._env_int("MD_ARCHIVE_TTL", 1800)
HC_FILES_TTL = perf._env_int("MD_HC_FILES_TTL", 900)
MAX_CANDIDATES = perf._env_int("MD_MAX_CANDIDATES", 6)
MAX_HC_BUTTONS = perf._env_int("MD_MAX_HC_BUTTONS", 3)
WARM_CANDIDATES = perf._env_int("MD_WARM_CANDIDATES", 2)

SKIP_SLUG_WORDS = ("category", "tag", "contact", "dmca", "privacy")
PACK_WORDS = ("zip", "pack", "complete", "season zip", "rar")
BUTTON_HOSTS = tuple(
    perf._env_list("MD_BUTTON_HOSTS")
    or ["hubcloud", "archive/", "mdrive.", "kolop", "katdrive", "fastdl"]
)
SERIES_PATTERN = re.compile(r"season|s\d+|series|episodes?|ep\d+", re.I)


# ------------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------------
def current_base() -> str:
    return get_active_base(MOVIESDRIVE_BASE_URL).rstrip("/")


def request_headers(referer: Optional[str] = None) -> Dict[str, str]:
    """Headers whose Referer follows the mirror that is actually in use."""
    return {
        "User-Agent": perf.USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer or (current_base() + "/"),
    }


def absolute(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http"):
        return url
    return urllib.parse.urljoin(current_base() + "/", url)


def strip_base(url: str) -> str:
    """Drop any known MoviesDrive host, so cache keys stay mirror independent."""
    out = url or ""
    for base in perf.known_bases() or ALL_BASES:
        out = out.replace(base, "")
    return out.strip("/")


def parse_quality_badge(title: str) -> str:
    t = (title or "").lower()
    if "2160p" in t or "4k" in t:
        return "4K UHD"
    if "1080p" in t:
        return "1080p FHD"
    if "720p" in t:
        return "720p HD"
    if "480p" in t:
        return "480p"
    return "HD"


def quality_rank(title: str) -> int:
    """Higher is better, so the qualities people pick get resolved first."""
    t = (title or "").lower()
    if "2160p" in t or "4k" in t:
        return 4
    if "1080p" in t:
        return 3
    if "720p" in t:
        return 2
    if "480p" in t:
        return 1
    return 0


def looks_like_series(title: str) -> bool:
    return bool(SERIES_PATTERN.search(title or ""))


def post_content(html_text: str):
    """Parse only the post body when possible - these pages are huge."""
    if not html_text:
        return make_soup("")
    for cls in ("entry-content", "post-layout", "thecontent", "post-content"):
        scoped = make_soup(html_text, only=SoupStrainer("div", class_=cls))
        if scoped and scoped.contents:
            return scoped
    full = make_soup(html_text)
    return (
        full.find(
            "div",
            class_=lambda c: c and any(
                k in c for k in ("entry-content", "post-layout", "thecontent", "post-content")
            ),
        )
        or full.find("article")
        or full
    )


# ------------------------------------------------------------------
# Level 1: MoviesDrive pages, with mirror racing
# ------------------------------------------------------------------
async def fetch_html(
    url: str,
    referer: Optional[str] = None,
    race: bool = True,
    validate: bool = True,
    _retry_discovery: bool = True,
) -> str:
    """Fetch a MoviesDrive page, racing the mirrors and rejecting junk bodies.

    A bot-challenge page is not a valid body (see perf.content_ok), so it can
    neither be parsed nor pin a broken mirror. When every mirror fails, the
    current domain is re-discovered once and the request is retried there.
    """
    headers = request_headers(referer)
    validator = content_ok if validate else None

    if race and base_of(url, perf.known_bases()):
        candidates = mirror_candidates(url, MOVIESDRIVE_BACKUP_URLS, MOVIESDRIVE_BASE_URL)
        text, _final_url = await race_fetch_text(
            candidates, headers=headers, validator=validator
        )
        if text:
            return text
        if _retry_discovery:
            discovered = await perf.discover_active_base(
                MOVIESDRIVE_BASE_URL, force=True
            )
            retry_url = perf.rebase(url, discovered) if discovered else url
            if discovered and retry_url != url:
                logger.info(
                    "MoviesDrive retrying %s on the newly discovered mirror %s",
                    url,
                    discovered,
                )
                return await fetch_html(
                    retry_url,
                    referer=referer,
                    race=False,
                    validate=validate,
                    _retry_discovery=False,
                )
        return ""

    text, _ = await fetch_text(url, headers=headers)
    if validate and text and not content_ok(text):
        logger.warning("MoviesDrive discarded an unusable body from %s", url)
        return ""
    return text


async def _scrape_buttons(post_url: str) -> List[Dict[str, Any]]:
    html_content = await fetch_html(post_url)
    if not html_content:
        logger.warning("MoviesDrive post page returned nothing: %s", post_url)
        return []
    content = post_content(html_content)
    results: List[Dict[str, Any]] = []
    seen = set()
    current_season = None

    for elem in content.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "div"]):
        text = elem.get_text(" ", strip=True)
        season_match = re.search(r"\bseason\s*(\d+)\b", text, re.I)
        if season_match:
            current_season = int(season_match.group(1))

        for a in elem.find_all("a", href=True):
            href = a["href"]
            if href in seen:
                continue
            btn_text = a.get_text(strip=True)
            if not any(host in href for host in BUTTON_HOSTS):
                continue
            if any(word in href.lower() for word in ("category", "tag", "telegram", "join")):
                continue
            btn_season = current_season
            bs_match = re.search(r"\bs(\d+)\b|\bseason\s*(\d+)\b", btn_text, re.I)
            if bs_match:
                btn_season = int(bs_match.group(1) or bs_match.group(2))
            seen.add(href)
            results.append({"text": btn_text, "url": href, "season": btn_season})
    if not results:
        logger.warning(
            "MoviesDrive found no download buttons on %s (hosts looked for: %s)",
            post_url,
            ", ".join(BUTTON_HOSTS),
        )
    return results


async def resolve_all_download_buttons_from_post(post_url: str) -> List[Dict[str, Any]]:
    """Cached list of download buttons on a post page."""
    return await cached_call(
        "post_buttons:" + strip_base(post_url),
        lambda: _scrape_buttons(post_url),
        ttl=POST_TTL,
        stale_ttl=POST_STALE_TTL,
        negative_ttl=NEGATIVE_TTL,
    ) or []


# ------------------------------------------------------------------
# Level 2: mdrive archive page -> hubcloud link for one episode
# ------------------------------------------------------------------
async def _scrape_archive(archive_url: str, post_url: str, episode_num: int) -> Optional[str]:
    text = await fetch_html(archive_url, referer=post_url, race=False)
    if not text:
        return None
    soup = make_soup(text)
    hc_links = [a["href"] for a in soup.find_all("a", href=True) if "hubcloud" in a["href"]]
    if len(hc_links) >= episode_num:
        return hc_links[episode_num - 1]
    logger.info(
        "MoviesDrive archive page %s has %s hubcloud links, episode %s requested",
        archive_url,
        len(hc_links),
        episode_num,
    )
    return None


async def resolve_archive_page_episodes(
    archive_url: str, post_url: str, episode_num: int = 1
) -> Optional[str]:
    return await cached_call(
        "arc:" + archive_url + ":" + str(episode_num),
        lambda: _scrape_archive(archive_url, post_url, episode_num),
        ttl=ARCHIVE_TTL,
        negative_ttl=NEGATIVE_TTL,
    )


# ------------------------------------------------------------------
# Level 3a: hubcloud search API -> individual files
# ------------------------------------------------------------------
def _hubcloud_token(page_html: str) -> Optional[str]:
    """HubCloud renames this constant now and then, so try a few shapes."""
    patterns = (
        r'const\s+FROM_AC_TOKEN\s*=\s*["\']([^"\']+)["\']',
        r'FROM_AC_TOKEN\s*[:=]\s*["\']([^"\']+)["\']',
        r'from_ac["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        r'name=["\']from_ac["\']\s+value=["\']([^"\']+)["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, page_html)
        if match:
            return match.group(1)
    return None


async def _scrape_hubcloud_files(
    hubcloud_url: str, filter_query: Optional[str]
) -> List[Dict[str, Any]]:
    page_html, final_url = await fetch_text(
        hubcloud_url,
        headers=request_headers(),
    )
    if not page_html:
        logger.warning("HubCloud page returned nothing: %s", hubcloud_url)
        return []

    token_val = _hubcloud_token(page_html)
    if not token_val:
        logger.warning(
            "HubCloud search token not found on %s (%s bytes) - the page layout "
            "probably changed",
            hubcloud_url,
            len(page_html),
        )
        return []

    q_match = re.search(r'const\s+Q_INITIAL\s*=\s*"([^"]+)"', page_html) or re.search(
        r'Q_INITIAL\s*[:=]\s*["\']([^"\']+)["\']', page_html
    )
    q_val = q_match.group(1) if q_match else ""
    try:
        q_val = q_val.encode("utf-8").decode("unicode-escape")
    except Exception:
        pass
    q_val = html_lib.unescape(q_val)
    clean_q = re.sub(r"[\r\n\t]", " ", q_val).strip()
    search_query = filter_query if filter_query else clean_q

    api_url = (
        HUBCLOUD_SEARCH_ENDPOINT
        + "?api=search&q="
        + urllib.parse.quote(search_query)
        + "&page=1&from_ac="
        + token_val
    )
    data = await perf.fetch_json(
        api_url,
        headers={"User-Agent": perf.USER_AGENT},
        referer=final_url or hubcloud_url,
    )
    if isinstance(data, dict):
        hits = data.get("hits") or []
        if not hits:
            logger.info("HubCloud search returned no hits for %r", search_query)
        return hits
    return []


async def resolve_hubcloud_files_from_url(
    hubcloud_url: str, filter_query: Optional[str] = None
) -> List[Dict[str, Any]]:
    return await cached_call(
        "hc_files:" + hubcloud_url + ":" + str(filter_query),
        lambda: _scrape_hubcloud_files(hubcloud_url, filter_query),
        ttl=HC_FILES_TTL,
        negative_ttl=NEGATIVE_TTL,
    ) or []


# ------------------------------------------------------------------
# Level 3b + 4: hubcloud file page -> gamerxyt -> direct CDN links
# ------------------------------------------------------------------
def _clean_direct_url(href: str) -> str:
    parts = urllib.parse.urlsplit(href)
    return urllib.parse.urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            urllib.parse.quote(parts.path),
            parts.query,
            parts.fragment,
        )
    )


def _is_pack_link(href: str, text: str) -> bool:
    if any(bad in href.lower() for bad in (".zip", ".rar")):
        return True
    return any(bad in (text or "").lower() for bad in ("zip", "pack"))


def _collect_stream_links(html_text: str) -> List[Dict[str, str]]:
    streams: List[Dict[str, str]] = []
    seen = set()
    media_fallback: List[Dict[str, str]] = []

    for a in make_soup(html_text).find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if not href.startswith("http") or href in seen:
            continue
        low = href.lower()
        if _is_pack_link(href, text):
            continue
        if any(host in low for host in FSL_HOSTS):
            seen.add(href)
            streams.append({"type": "FSL Server (Cloudflare R2 10Gbps)", "url": href})
        elif any(host in low for host in WORKER_HOSTS):
            seen.add(href)
            streams.append({"type": "Worker CDN 10Gbps", "url": _clean_direct_url(href)})
        elif EXTRA_DIRECT_HOSTS and any(host in low for host in EXTRA_DIRECT_HOSTS):
            seen.add(href)
            streams.append({"type": "Direct CDN", "url": _clean_direct_url(href)})
        elif any(low.split("?")[0].endswith(ext) for ext in MEDIA_EXTENSIONS):
            media_fallback.append(
                {"type": "Direct file", "url": _clean_direct_url(href)}
            )

    return streams or media_fallback


async def _scrape_direct_streams(hubcloud_file_url: str) -> List[Dict[str, str]]:
    first_html, _ = await fetch_text(
        hubcloud_file_url,
        headers={"User-Agent": perf.USER_AGENT},
        referer=HUBCLOUD_BASE + "/",
    )
    if not first_html:
        logger.warning("HubCloud file page returned nothing: %s", hubcloud_file_url)
        return []

    soup1 = make_soup(first_html)
    gamer_link = None
    for a in soup1.find_all("a", href=True):
        if any(host in a["href"] for host in GAMERXYT_HOSTS):
            gamer_link = a["href"]
            break

    if not gamer_link:
        # Some file pages already expose the CDN links directly.
        direct = _collect_stream_links(first_html)
        if direct:
            return direct
        logger.warning(
            "No %s link on %s and no direct CDN link either",
            "/".join(GAMERXYT_HOSTS),
            hubcloud_file_url,
        )
        return []

    second_html, _ = await fetch_text(
        gamer_link,
        headers={"User-Agent": perf.USER_AGENT},
        referer=hubcloud_file_url,
    )
    if not second_html:
        logger.warning("GamerXYT page returned nothing: %s", gamer_link)
        return []

    streams = _collect_stream_links(second_html)
    if not streams:
        logger.warning(
            "GamerXYT page %s had no usable link (looked for %s)",
            gamer_link,
            ", ".join(FSL_HOSTS + WORKER_HOSTS + EXTRA_DIRECT_HOSTS),
        )
    return streams


async def resolve_direct_stream_links(hubcloud_file_url: str) -> List[Dict[str, str]]:
    return await cached_call(
        "stream:" + hubcloud_file_url,
        lambda: _scrape_direct_streams(hubcloud_file_url),
        ttl=STREAM_CACHE_TTL,
        negative_ttl=NEGATIVE_TTL,
    ) or []


def pick_best_stream(streams: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    if not streams:
        return None
    for item in streams:
        if any(host in item.get("url", "").lower() for host in FSL_HOSTS):
            return item
    return streams[0]


# ------------------------------------------------------------------
# Candidates: everything we know after ONE request
# ------------------------------------------------------------------
def _is_pack(text: str) -> bool:
    low = (text or "").lower()
    return any(word in low for word in PACK_WORDS)


async def collect_candidates(
    post_url: str,
    media_type: str = "movie",
    season_num: Optional[int] = None,
    episode_num: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return playable candidates, resolved lazily later.

    Each candidate carries either an archive_url (needs levels 2-4) or a
    hubcloud_url (needs levels 3-4).
    """
    buttons = await resolve_all_download_buttons_from_post(post_url)
    if not buttons:
        return []

    target_ep = episode_num if (media_type == "series" and episode_num) else 1

    archive_buttons = [
        b
        for b in buttons
        if ("archive/" in b["url"] or "mdrive." in b["url"]) and not _is_pack(b["text"])
    ]
    if season_num is not None:
        season_matched = [b for b in archive_buttons if b.get("season") == season_num]
        if season_matched:
            archive_buttons = season_matched

    candidates: List[Dict[str, Any]] = []
    for button in archive_buttons:
        candidates.append(
            {
                "label": button["text"],
                "quality": parse_quality_badge(button["text"]),
                "rank": quality_rank(button["text"]),
                "archive_url": button["url"],
                "hubcloud_url": None,
                "episode": target_ep,
                "post_url": post_url,
                "size": "",
            }
        )

    if candidates:
        candidates.sort(key=lambda c: c["rank"], reverse=True)
        return candidates[:MAX_CANDIDATES]

    # Fallback: hubcloud search-recover buttons
    hc_buttons = [b for b in buttons if "hubcloud" in b["url"]][:MAX_HC_BUTTONS]
    if not hc_buttons:
        logger.info("No archive or hubcloud button usable on %s", post_url)
        return []

    filter_q = None
    if season_num is not None and episode_num is not None:
        filter_q = "S" + str(season_num).zfill(2) + "E" + str(episode_num).zfill(2)

    results = await asyncio.gather(
        *[resolve_hubcloud_files_from_url(b["url"], filter_query=filter_q) for b in hc_buttons],
        return_exceptions=True,
    )

    seen_urls = set()
    for result in results:
        if not isinstance(result, list):
            continue
        for item in result:
            file_url = item.get("url")
            if not file_url or file_url in seen_urls:
                continue
            file_name = item.get("file_name", "")
            if season_num is not None and episode_num is not None:
                pattern = (
                    r"S0?" + str(season_num) + r".*?E0?" + str(episode_num) + r"\b"
                    r"|EP0?" + str(episode_num) + r"\b"
                )
                if not re.search(pattern, file_name, re.I):
                    continue
            seen_urls.add(file_url)
            candidates.append(
                {
                    "label": file_name or "MoviesDrive",
                    "quality": parse_quality_badge(file_name),
                    "rank": quality_rank(file_name),
                    "archive_url": None,
                    "hubcloud_url": file_url,
                    "episode": target_ep,
                    "post_url": post_url,
                    "size": item.get("size", ""),
                }
            )

    candidates.sort(key=lambda c: c["rank"], reverse=True)
    return candidates[:MAX_CANDIDATES]


# ------------------------------------------------------------------
# Lazy resolution, used by /moviesdrive/resolve and by the warmer
# ------------------------------------------------------------------
async def resolve_playable_url(
    archive_url: Optional[str] = None,
    hubcloud_url: Optional[str] = None,
    post_url: Optional[str] = None,
    episode: int = 1,
) -> Optional[Dict[str, str]]:
    hc_url = hubcloud_url
    if not hc_url and archive_url:
        hc_url = await resolve_archive_page_episodes(
            archive_url, post_url or (current_base() + "/"), episode_num=episode
        )
    if not hc_url:
        return None
    streams = await resolve_direct_stream_links(hc_url)
    return pick_best_stream(streams)


async def resolve_candidate(candidate: Dict[str, Any]) -> Optional[Dict[str, str]]:
    return await resolve_playable_url(
        archive_url=candidate.get("archive_url"),
        hubcloud_url=candidate.get("hubcloud_url"),
        post_url=candidate.get("post_url"),
        episode=int(candidate.get("episode") or 1),
    )


async def warm_candidates(
    candidates: List[Dict[str, Any]], limit: int = WARM_CANDIDATES
) -> Optional[Dict[str, str]]:
    """Resolve the top candidates in the background so play is instant."""
    if not candidates:
        return None
    results = await asyncio.gather(
        *[resolve_candidate(c) for c in candidates[:limit]], return_exceptions=True
    )
    for item in results:
        if isinstance(item, dict) and item.get("url"):
            return item
    return None
