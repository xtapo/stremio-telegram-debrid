"""
Link resolving layer for HDHub4u addon.

A HDHub4u lookup chain:
    post page -> [hubdrive / hubcdn / hubcloud / gamerxyt] -> direct CDN stream (Cloudflare R2 / Pixel CDN)

Fast 2-phase resolution:
1. collect_candidates(): parses post page only and builds Stremio stream items immediately.
2. resolve_playable_url(): resolves the specific stream on Play (or background prewarm).
"""

import asyncio
import base64
import html as html_lib
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from bs4 import SoupStrainer

import hdhub4u_perf as perf
from hdhub4u_perf import (
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

logger = logging.getLogger("hdhub4u_addon")

HUBCLOUD_BASE = "https://hubcloud.cx"
GAMERXYT_BASE = "https://gamerxyt.com/"

POST_TTL = perf._env_int("HDH_POST_TTL", 900)
POST_STALE_TTL = perf._env_int("HDH_POST_STALE_TTL", 3600)
HUBDRIVE_TTL = perf._env_int("HDH_HUBDRIVE_TTL", 1800)
HUBCDN_TTL = perf._env_int("HDH_HUBCDN_TTL", 1800)
HC_FILES_TTL = perf._env_int("HDH_HC_FILES_TTL", 900)
MAX_CANDIDATES = perf._env_int("HDH_MAX_CANDIDATES", 8)
WARM_CANDIDATES = perf._env_int("HDH_WARM_CANDIDATES", 2)

SKIP_WORDS = (
    "category", "tag", "contact", "dmca", "privacy", "how-to-download",
    "disclaimer", "join-our-group", "request-a-movie", "snvhost", "whatsapp",
    "catimages", "4khdhub", "sharethis", "google", "facebook", "twitter",
    "comment", "cinevood", "trailer",
)
PACK_WORDS = ("zip", "pack", "complete", "season zip", "rar")
DOWNLOAD_HOSTS = ("hubdrive.", "hubcdn.", "hubcloud.", "greenmountmotors.", "hdstream4u.", "hubstream.")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def current_base() -> str:
    return get_active_base(perf.HDHUB4U_BASE_DEFAULT).rstrip("/")


def absolute(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http"):
        return url
    return urllib.parse.urljoin(current_base() + "/", url)


def strip_base(url: str) -> str:
    out = url or ""
    for base in perf.HDHUB4U_BACKUP_URLS:
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
        return "480p SD"
    if "hevc" in t or "10bit" in t or "x265" in t:
        return "HEVC"
    return "HD"


def quality_rank(text: str) -> int:
    t = (text or "").lower()
    rank = 0
    if "2160p" in t or "4k" in t:
        rank += 400
    elif "1080p" in t:
        rank += 300
    elif "720p" in t:
        rank += 200
    elif "480p" in t:
        rank += 100

    if "10bit" in t or "hevc" in t or "x265" in t:
        rank += 50
    if "web-dl" in t or "bluray" in t:
        rank += 20
    if "dual audio" in t or "hindi" in t:
        rank += 10
    if "hubcloud" in t or "hubdrive" in t or "hubcdn" in t or "instant" in t:
        rank += 5
    return rank


def post_content(html: str) -> BeautifulSoup:
    return make_soup(
        html,
        only=SoupStrainer(["div", "article", "section", "main", "p", "h1", "h2", "h3", "h4", "h5", "h6"]),
    )


# ------------------------------------------------------------------
# Level 1: HDHub4u Post Scraping
# ------------------------------------------------------------------
async def fetch_html(url: str, referer: Optional[str] = None, race: bool = True) -> str:
    headers = dict(perf.DEFAULT_HEADERS)
    if referer:
        headers["Referer"] = referer

    if race and base_of(url, perf.HDHUB4U_BACKUP_URLS):
        candidates = mirror_candidates(url, perf.HDHUB4U_BACKUP_URLS, perf.HDHUB4U_BASE_DEFAULT)
        text, final_url = await race_fetch_text(candidates, headers=headers)
        if text:
            winner = base_of(final_url, perf.HDHUB4U_BACKUP_URLS)
            if winner:
                note_active_base(winner)
        return text

    text, _ = await fetch_text(url, headers=headers)
    return text


async def _scrape_buttons(post_url: str) -> List[Dict[str, Any]]:
    html_content = await fetch_html(post_url)
    if not html_content:
        return []
    soup = make_soup(html_content)
    results: List[Dict[str, Any]] = []
    seen = set()

    current_season = 1
    current_episode = 1

    for elem in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "center"]):
        text = elem.get_text(" ", strip=True)

        season_match = re.search(r"\bseason\s*(\d+)\b", text, re.I)
        if season_match:
            current_season = int(season_match.group(1))

        ep_match = re.search(r"\b(?:episode|ep)\s*0*(\d+)\b", text, re.I)
        if ep_match:
            current_episode = int(ep_match.group(1))

        for a in elem.find_all("a", href=True):
            href = a["href"]
            if href in seen:
                continue
            btn_text = a.get_text(strip=True)
            if not btn_text:
                btn_text = text

            if any(skip in href.lower() for skip in SKIP_WORDS):
                continue
            if not any(h in href.lower() for h in DOWNLOAD_HOSTS) and not any(
                p in href.lower() for p in ("/file/", "/drive/", "/dl/")
            ):
                continue

            btn_season = current_season
            btn_ep = current_episode

            bs_match = re.search(r"\bs0*(\d+)\b|\bseason\s*0*(\d+)\b", btn_text, re.I)
            if bs_match:
                btn_season = int(bs_match.group(1) or bs_match.group(2))

            be_match = re.search(r"\be0*(\d+)\b|\bep(?:isode)?\s*0*(\d+)\b", btn_text, re.I)
            if be_match:
                btn_ep = int(be_match.group(1) or be_match.group(2))

            # Look for file size in tag text
            size_match = re.search(r"\[([\d\.]+\s*(?:GB|MB))\]|\(([\d\.]+\s*(?:GB|MB))\)", text + " " + btn_text, re.I)
            size_str = size_match.group(1) or size_match.group(2) if size_match else ""

            combined_label = f"{text} - {btn_text}".strip(" -")
            if len(combined_label) > 120:
                combined_label = btn_text or text[:100]

            seen.add(href)
            results.append({
                "text": combined_label,
                "url": href,
                "season": btn_season,
                "episode": btn_ep,
                "size": size_str,
            })
    return results


async def resolve_all_download_buttons_from_post(post_url: str) -> List[Dict[str, Any]]:
    return await cached_call(
        "hdh_post_buttons:" + strip_base(post_url),
        lambda: _scrape_buttons(post_url),
        ttl=POST_TTL,
        stale_ttl=POST_STALE_TTL,
        negative_ttl=NEGATIVE_TTL,
    ) or []


# ------------------------------------------------------------------
# Level 2: HubDrive / HubCDN / HubCloud intermediate resolution
# ------------------------------------------------------------------
async def _resolve_hubdrive(hubdrive_url: str) -> Optional[str]:
    """Scrapes HubDrive page (e.g. hubdrive.tips/file/...) to extract HubCloud link."""
    text, _ = await fetch_text(hubdrive_url, headers=perf.DEFAULT_HEADERS)
    if not text:
        return None
    soup = make_soup(text)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "hubcloud" in href and "/drive/" in href:
            return href
    # Check if direct link is present
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "gamerxyt.com" in href:
            return href
    return None


async def resolve_hubdrive(hubdrive_url: str) -> Optional[str]:
    return await cached_call(
        "hdh_hubdrive:" + hubdrive_url,
        lambda: _resolve_hubdrive(hubdrive_url),
        ttl=HUBDRIVE_TTL,
        negative_ttl=NEGATIVE_TTL,
    )


async def _resolve_hubcdn(hubcdn_url: str) -> Optional[str]:
    """Scrapes HubCDN (e.g. hubcdn.sbs/file/...) to extract direct R2 storage link."""
    text, _ = await fetch_text(hubcdn_url, headers=perf.DEFAULT_HEADERS)
    if not text:
        return None

    # Search for encoded redirect URL
    m = re.search(r'var\s+reurl\s*=\s*"[^"]*[?&]r=([A-Za-z0-9+/=]+)"', text)
    if m:
        try:
            decoded = base64.b64decode(m.group(1)).decode("utf-8", "ignore")
            # decoded is e.g. https://hubcdn.sbs/dl/?link=https://pub-...r2.dev/...
            link_match = re.search(r"link=(https?://[^\s&]+)", decoded)
            if link_match:
                return link_match.group(1)
            if decoded.startswith("http"):
                return decoded
        except Exception:
            pass

    # Look for direct link in soup
    soup = make_soup(text)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "r2.dev" in href or "cloudflarestorage.com" in href:
            return href
    return None


async def resolve_hubcdn(hubcdn_url: str) -> Optional[str]:
    return await cached_call(
        "hdh_hubcdn:" + hubcdn_url,
        lambda: _resolve_hubcdn(hubcdn_url),
        ttl=HUBCDN_TTL,
        negative_ttl=NEGATIVE_TTL,
    )


# ------------------------------------------------------------------
# Level 3 & 4: HubCloud -> GamerXYT -> Direct CDN Stream Links
# ------------------------------------------------------------------
async def _scrape_direct_streams(hubcloud_file_url: str) -> List[Dict[str, str]]:
    first_html, _ = await fetch_text(
        hubcloud_file_url,
        headers=perf.DEFAULT_HEADERS,
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
        # Check if direct download links exist on the first page
        direct_streams = []
        for a in soup1.find_all("a", href=True):
            href = a["href"]
            if "r2.cloudflarestorage.com" in href or "r2.dev" in href:
                direct_streams.append({"type": "FSL Server (Cloudflare R2 10Gbps)", "url": href})
        if direct_streams:
            return direct_streams
        return []

    second_html, _ = await fetch_text(
        gamer_link,
        headers=perf.DEFAULT_HEADERS,
        referer=hubcloud_file_url,
    )
    if not second_html:
        return []

    streams: List[Dict[str, str]] = []
    soup2 = make_soup(second_html)
    for a in soup2.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)

        if "cloudflarestorage.com" in href or "r2.dev" in href:
            if any(bad in href.lower() for bad in (".zip", ".rar")) or any(bad in text.lower() for bad in ("zip", "pack")):
                continue
            streams.append({"type": "FSL Server (Cloudflare R2 10Gbps)", "url": href})
        elif "pixel.hubcloud" in href or "pixeldrain" in href:
            streams.append({"type": "Pixel CDN 10Gbps", "url": href})
        elif "workers.dev" in href:
            parts = urllib.parse.urlsplit(href)
            clean_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, urllib.parse.quote(parts.path), parts.query, parts.fragment))
            streams.append({"type": "Worker CDN 10Gbps", "url": clean_url})
        elif "bzzhr.co" in href or "buzz" in text.lower():
            streams.append({"type": "Buzz Server Fast", "url": href})

    return streams


async def resolve_direct_stream_links(hubcloud_file_url: str) -> List[Dict[str, str]]:
    return await cached_call(
        "hdh_stream:" + hubcloud_file_url,
        lambda: _scrape_direct_streams(hubcloud_file_url),
        ttl=STREAM_CACHE_TTL,
        negative_ttl=NEGATIVE_TTL,
    ) or []


def pick_best_stream(streams: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    if not streams:
        return None
    # Cloudflare R2 offers fastest instant streaming
    for item in streams:
        url = item.get("url", "")
        if "cloudflarestorage.com" in url or "r2.dev" in url:
            return item
    for item in streams:
        url = item.get("url", "")
        if "pixel" in url or "workers.dev" in url:
            return item
    return streams[0]


# ------------------------------------------------------------------
# Candidates Collection (Fast Pass)
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
    buttons = await resolve_all_download_buttons_from_post(post_url)
    if not buttons:
        return []

    target_ep = episode_num if (media_type == "series" and episode_num is not None) else None
    target_sn = season_num if (media_type == "series" and season_num is not None) else None

    # Filter out zip/pack files if looking for single episode
    filtered = [b for b in buttons if not _is_pack(b.get("text", ""))]
    if not filtered:
        filtered = buttons

    if target_sn is not None:
        season_matched = [b for b in filtered if b.get("season") == target_sn]
        if season_matched:
            filtered = season_matched

    if target_ep is not None:
        ep_matched = [b for b in filtered if b.get("episode") == target_ep]
        if ep_matched:
            filtered = ep_matched

    candidates: List[Dict[str, Any]] = []
    seen_urls = set()

    for button in filtered:
        url = button["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)

        label = button["text"]
        q_badge = parse_quality_badge(label)
        rank = quality_rank(label)

        candidates.append({
            "label": label,
            "quality": q_badge,
            "rank": rank,
            "raw_url": url,
            "season": button.get("season"),
            "episode": button.get("episode"),
            "post_url": post_url,
            "size": button.get("size", ""),
        })

    candidates.sort(key=lambda c: c["rank"], reverse=True)
    return candidates[:MAX_CANDIDATES]


# ------------------------------------------------------------------
# Resolve Final Playable URL
# ------------------------------------------------------------------
async def resolve_playable_url(candidate: Dict[str, Any]) -> Optional[str]:
    raw_url = candidate.get("raw_url", "")
    if not raw_url:
        return None

    # 1. Direct HubCDN (Cloudflare R2)
    if "hubcdn." in raw_url:
        r2_url = await resolve_hubcdn(raw_url)
        if r2_url:
            return r2_url

    # 2. HubDrive
    hubcloud_url = None
    if "hubdrive." in raw_url:
        hubcloud_url = await resolve_hubdrive(raw_url)
    elif "hubcloud." in raw_url:
        hubcloud_url = raw_url

    # 3. HubCloud -> GamerXYT direct CDN streams
    if hubcloud_url:
        streams = await resolve_direct_stream_links(hubcloud_url)
        best = pick_best_stream(streams)
        if best:
            return best.get("url")

    # 4. Fallback: try raw URL if already direct
    if any(ext in raw_url.lower() for ext in (".mkv", ".mp4", ".m3u8")):
        return raw_url

    return None


async def resolve_candidate(candidate: Dict[str, Any]) -> Optional[str]:
    cache_key = "hdh_playable:" + candidate.get("raw_url", "")
    return await cached_call(
        cache_key,
        lambda: resolve_playable_url(candidate),
        ttl=STREAM_CACHE_TTL,
        negative_ttl=NEGATIVE_TTL,
    )


def warm_candidates(candidates: List[Dict[str, Any]], count: int = WARM_CANDIDATES) -> None:
    for cand in (candidates or [])[:count]:
        try:
            asyncio.create_task(resolve_candidate(cand))
        except RuntimeError:
            pass
