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
"""

import asyncio
import html as html_lib
import logging
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
    fetch_text,
    get_active_base,
    make_soup,
    mirror_candidates,
    note_active_base,
    race_fetch_text,
)

logger = logging.getLogger("moviesdrive_addon")

MOVIESDRIVE_BASE_URL = "https://new2.moviesdrive.christmas"
MOVIESDRIVE_BACKUP_URLS = [
    "https://new2.moviesdrive.christmas",
    "https://new1.moviesdrive.christmas",
    "https://moviesdrives.mov",
]
ALL_BASES = list(dict.fromkeys(MOVIESDRIVE_BACKUP_URLS + [MOVIESDRIVE_BASE_URL]))

HUBCLOUD_BASE = "https://hubcloud.cx"
HUBCLOUD_SEARCH_ENDPOINT = HUBCLOUD_BASE + "/drive/search-recover.php"
GAMERXYT_BASE = "https://gamerxyt.com/"

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
BUTTON_HOSTS = ("hubcloud", "archive/", "mdrive.", "kolop", "katdrive", "fastdl")
SERIES_PATTERN = re.compile(r"season|s\d+|series|episodes?|ep\d+", re.I)


# ------------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------------
def current_base() -> str:
    return get_active_base(MOVIESDRIVE_BASE_URL).rstrip("/")


def absolute(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http"):
        return url
    return urllib.parse.urljoin(current_base() + "/", url)


def strip_base(url: str) -> str:
    out = url or ""
    for base in ALL_BASES:
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
    scoped = make_soup(html_text, only=SoupStrainer("div", class_="entry-content"))
    if scoped.contents:
        return scoped
    full = make_soup(html_text)
    return full.find("div", class_="entry-content") or full.find("article") or full


# ------------------------------------------------------------------
# Level 1: MoviesDrive pages, with mirror racing
# ------------------------------------------------------------------
async def fetch_html(url: str, referer: Optional[str] = None, race: bool = True) -> str:
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer

    if race and base_of(url, ALL_BASES):
        candidates = mirror_candidates(url, MOVIESDRIVE_BACKUP_URLS, MOVIESDRIVE_BASE_URL)
        text, final_url = await race_fetch_text(candidates, headers=headers)
        if text:
            winner = base_of(final_url, ALL_BASES)
            if winner:
                note_active_base(winner)
        return text

    text, _ = await fetch_text(url, headers=headers)
    return text


async def _scrape_buttons(post_url: str) -> List[Dict[str, Any]]:
    html_content = await fetch_html(post_url)
    if not html_content:
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
async def _scrape_hubcloud_files(
    hubcloud_url: str, filter_query: Optional[str]
) -> List[Dict[str, Any]]:
    page_html, final_url = await fetch_text(
        hubcloud_url,
        headers={"User-Agent": perf.USER_AGENT},
        referer=current_base() + "/",
    )
    if not page_html:
        return []

    token_match = re.search(r'const FROM_AC_TOKEN\s*=\s*"([^"]+)"', page_html)
    if not token_match:
        return []
    token_val = token_match.group(1)

    q_match = re.search(r'const Q_INITIAL\s*=\s*"([^"]+)"', page_html)
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
        return data.get("hits", []) or []
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
async def _scrape_direct_streams(hubcloud_file_url: str) -> List[Dict[str, str]]:
    first_html, _ = await fetch_text(
        hubcloud_file_url,
        headers={"User-Agent": perf.USER_AGENT},
        referer=HUBCLOUD_BASE + "/",
    )
    if not first_html:
        return []
    soup1 = make_soup(first_html)
    gamer_link = None
    for a in soup1.find_all("a", href=True):
        if "gamerxyt.com" in a["href"]:
            gamer_link = a["href"]
            break
    if not gamer_link:
        return []

    second_html, _ = await fetch_text(
        gamer_link,
        headers={"User-Agent": perf.USER_AGENT},
        referer=hubcloud_file_url,
    )
    if not second_html:
        return []

    streams: List[Dict[str, str]] = []
    for a in make_soup(second_html).find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if "cloudflarestorage.com" in href:
            if any(bad in href.lower() for bad in (".zip", ".rar")):
                continue
            if any(bad in text.lower() for bad in ("zip", "pack")):
                continue
            streams.append({"type": "FSL Server (Cloudflare R2 10Gbps)", "url": href})
        elif "workers.dev" in href:
            parts = urllib.parse.urlsplit(href)
            clean_url = urllib.parse.urlunsplit(
                (
                    parts.scheme,
                    parts.netloc,
                    urllib.parse.quote(parts.path),
                    parts.query,
                    parts.fragment,
                )
            )
            streams.append({"type": "Worker CDN 10Gbps", "url": clean_url})
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
        if "cloudflarestorage.com" in item.get("url", ""):
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
