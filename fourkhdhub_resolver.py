"""
Link resolving layer for 4KHDHub addon.

A 4KHDHub lookup chain:
    post page -> [hubcloud / hubdrive / gamerxyt] -> direct CDN stream (Cloudflare R2 10Gbps / HubCloud GPDL / PixelDrain)

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

from bs4 import BeautifulSoup, SoupStrainer

import fourkhdhub_perf as perf
from fourkhdhub_perf import (
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

logger = logging.getLogger("fourkhdhub_addon")

HUBCLOUD_BASE = "https://hubcloud.cx"
GAMERXYT_BASE = "https://gamerxyt.com/"

POST_TTL = perf._env_int("FOURKHD_POST_TTL", 900)
POST_STALE_TTL = perf._env_int("FOURKHD_POST_STALE_TTL", 3600)
HUBDRIVE_TTL = perf._env_int("FOURKHD_HUBDRIVE_TTL", 1800)
HUBCDN_TTL = perf._env_int("FOURKHD_HUBCDN_TTL", 1800)
HC_FILES_TTL = perf._env_int("FOURKHD_HC_FILES_TTL", 900)
MAX_CANDIDATES = perf._env_int("FOURKHD_MAX_CANDIDATES", 8)
WARM_CANDIDATES = perf._env_int("FOURKHD_WARM_CANDIDATES", 2)

SKIP_WORDS = (
    "category", "tag", "contact", "dmca", "privacy", "how-to-download",
    "disclaimer", "join-our-group", "request-a-movie", "snvhost", "whatsapp",
    "sharethis", "google", "facebook", "twitter", "comment", "trailer",
)
PACK_WORDS = ("zip", "pack", "complete", "season zip", "rar")
DOWNLOAD_HOSTS = ("hubdrive.", "hubcdn.", "hubcloud.", "gamerxyt.", "gdflix.")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def current_base() -> str:
    return get_active_base(perf.FOURKHDHUB_BASE_DEFAULT).rstrip("/")


def absolute(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http"):
        return url
    return urllib.parse.urljoin(current_base() + "/", url)


def strip_base(url: str) -> str:
    out = url or ""
    for base in perf.FOURKHDHUB_BACKUP_URLS:
        out = out.replace(base, "")
    return out.strip("/")


def parse_quality_badge(title: str) -> str:
    t = (title or "").lower()
    if "2160p" in t or "4k" in t:
        if "remux" in t:
            return "4K UHD REMUX"
        if "dv" in t or "dovi" in t or "dolby vision" in t:
            return "4K Dolby Vision"
        if "hdr" in t:
            return "4K HDR"
        return "4K UHD"
    if "1080p" in t:
        if "remux" in t:
            return "1080p REMUX"
        if "hevc" in t or "10bit" in t or "x265" in t:
            return "1080p HEVC"
        return "1080p FHD"
    if "720p" in t:
        return "720p HD"
    if "480p" in t:
        return "480p SD"
    if "hevc" in t or "10bit" in t or "x265" in t:
        return "HEVC 10Bit"
    return "HD"


def quality_rank(text: str) -> int:
    t = (text or "").lower()
    rank = 0
    if "2160p" in t or "4k" in t:
        rank += 400
    elif "1080p" in t:
        rank += 200
    elif "720p" in t:
        rank += 100
    elif "480p" in t:
        rank += 50

    if "remux" in t:
        rank += 60
    if "dv" in t or "dovi" in t or "dolby vision" in t:
        rank += 50
    if "hdr" in t or "hdr10" in t:
        rank += 40
    if "imax" in t:
        rank += 35
    if "10bit" in t:
        rank += 25
    if "hevc" in t or "x265" in t or "h.265" in t or "h265" in t:
        rank += 20
    if "bluray" in t or "blu-ray" in t:
        rank += 15
    if "web-dl" in t or "webdl" in t:
        rank += 10
    if "atmos" in t or "ddp5.1" in t or "dts" in t:
        rank += 10
    return rank


# ------------------------------------------------------------------
# Post Page Fetching & Button Extraction
# ------------------------------------------------------------------
async def get_post_page(url_or_slug: str) -> Optional[str]:
    clean_url = absolute(url_or_slug)
    candidates = mirror_candidates(clean_url)
    key = "fourkhd_post:" + candidates[0]
    res = await cached_call(
        key,
        lambda: race_fetch_text(candidates),
        ttl=POST_TTL,
        stale_ttl=POST_STALE_TTL,
        negative_ttl=NEGATIVE_TTL,
    )
    if isinstance(res, tuple):
        return res[0]
    return res


def _extract_season_episode(text: str) -> Tuple[Optional[int], Optional[int]]:
    if not text:
        return None, None
    t = text.lower()
    
    # S01E02 or S1E2 or S01 E02
    m = re.search(r"s(\d{1,2})\s*e(\d{1,3})", t)
    if m:
        return int(m.group(1)), int(m.group(2))

    # Episode-01 or Episode 01 or Ep 01
    m_ep = re.search(r"(?:episode|ep)[\s\-_]*(\d{1,3})", t)
    ep = int(m_ep.group(1)) if m_ep else None

    # Season 01 or S01
    m_s = re.search(r"(?:season|s)[\s\-_]*(\d{1,2})", t)
    season = int(m_s.group(1)) if m_s else None

    return season, ep


async def _parse_post_buttons(post_url: str) -> List[Dict[str, Any]]:
    html = await get_post_page(post_url)
    if not html:
        return []

    soup = make_soup(html)
    buttons: List[Dict[str, Any]] = []
    seen_urls = set()

    # 1. Check for single episodes in TV Series (.episode-download-item)
    for ep_item in soup.select(".episode-download-item"):
        file_title_el = ep_item.select_one(".episode-file-title")
        file_title = file_title_el.get_text(strip=True) if file_title_el else ""

        info_el = ep_item.select_one(".episode-file-info")
        info_text = info_el.get_text(" ", strip=True) if info_el else ""

        size_el = ep_item.select_one(".badge-size")
        size = size_el.get_text(strip=True) if size_el else ""

        combined_text = f"{file_title} {info_text}"
        s_num, ep_num = _extract_season_episode(combined_text)

        links = ep_item.select("a[href]")
        for a in links:
            href = a["href"].strip()
            if not href or href in seen_urls:
                continue
            if any(host in href for host in DOWNLOAD_HOSTS) or "gamerxyt" in href:
                seen_urls.add(href)
                btn_txt = a.get_text(strip=True)
                full_label = f"{file_title or btn_txt}"
                buttons.append({
                    "text": full_label,
                    "url": href,
                    "season": s_num,
                    "episode": ep_num,
                    "size": size,
                    "type": "episode",
                    "file_title": file_title,
                })

    # 2. Check for movies / season packs (.download-item)
    for dl_item in soup.select(".download-item"):
        ep_badge = dl_item.select_one(".episode-number")
        ep_tag = ep_badge.get_text(strip=True) if ep_badge else ""

        header_title_el = dl_item.select_one(".download-header .font-semibold")
        header_title = header_title_el.get_text(" ", strip=True) if header_title_el else ""

        file_title_el = dl_item.select_one(".file-title")
        file_title = file_title_el.get_text(strip=True) if file_title_el else ""

        badges = [b.get_text(strip=True) for b in dl_item.select(".badge")]
        size = next((b for b in badges if "gb" in b.lower() or "mb" in b.lower()), "")

        combined_text = f"{ep_tag} {header_title} {file_title} {' '.join(badges)}"
        s_num, ep_num = _extract_season_episode(combined_text)

        links = dl_item.select("a[href]")
        for a in links:
            href = a["href"].strip()
            if not href or href in seen_urls:
                continue
            if any(host in href for host in DOWNLOAD_HOSTS) or "gamerxyt" in href:
                seen_urls.add(href)
                btn_txt = a.get_text(strip=True)
                full_label = file_title or header_title or btn_txt
                buttons.append({
                    "text": full_label,
                    "url": href,
                    "season": s_num,
                    "episode": ep_num,
                    "size": size,
                    "type": "movie" if not s_num and not ep_num else "season",
                    "file_title": file_title or header_title,
                })

    # 3. Fallback: parse any download anchor tags
    if not buttons:
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href in seen_urls:
                continue
            if any(host in href for host in DOWNLOAD_HOSTS):
                seen_urls.add(href)
                parent = a.find_parent(["div", "li", "p", "tr"])
                parent_text = parent.get_text(" ", strip=True) if parent else ""
                btn_text = a.get_text(strip=True)
                combined = f"{btn_text} {parent_text}"
                s_num, ep_num = _extract_season_episode(combined)
                buttons.append({
                    "text": btn_text or parent_text[:80],
                    "url": href,
                    "season": s_num,
                    "episode": ep_num,
                    "size": "",
                    "type": "fallback",
                    "file_title": btn_text,
                })

    return buttons


async def resolve_all_download_buttons_from_post(post_url: str) -> List[Dict[str, Any]]:
    clean_url = absolute(post_url)
    return await cached_call(
        "fourkhd_buttons:" + clean_url,
        lambda: _parse_post_buttons(clean_url),
        ttl=POST_TTL,
        stale_ttl=POST_STALE_TTL,
        negative_ttl=NEGATIVE_TTL,
    ) or []


# ------------------------------------------------------------------
# Level 2 & 3: HubDrive -> HubCloud / Direct
# ------------------------------------------------------------------
async def _resolve_hubdrive(hubdrive_url: str) -> Optional[str]:
    """Scrapes HubDrive (hubdrive.tips/file/... or hubdrive.wales/file/...) to get HubCloud link."""
    text, _ = await fetch_text(hubdrive_url, headers=perf.DEFAULT_HEADERS)
    if not text:
        return None

    soup = make_soup(text)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "hubcloud." in href:
            return href
        if "gamerxyt.com" in href:
            return href
        if "r2.cloudflarestorage.com" in href or "r2.dev" in href or "gpdl.hubcloud" in href:
            return href
    return None


async def resolve_hubdrive(hubdrive_url: str) -> Optional[str]:
    return await cached_call(
        "fourkhd_hubdrive:" + hubdrive_url,
        lambda: _resolve_hubdrive(hubdrive_url),
        ttl=HUBDRIVE_TTL,
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
            elif "gpdl.hubcloud" in href:
                direct_streams.append({"type": "HubCloud 10Gbps Server", "url": href})
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
        elif "gpdl.hubcloud" in href:
            streams.append({"type": "HubCloud 10Gbps Server", "url": href})
        elif "pixeldrain" in href or "pixel.hubcloud" in href:
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
        "fourkhd_stream:" + hubcloud_file_url,
        lambda: _scrape_direct_streams(hubcloud_file_url),
        ttl=STREAM_CACHE_TTL,
        negative_ttl=NEGATIVE_TTL,
    ) or []


def pick_best_stream(streams: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    if not streams:
        return None
    # 1. Cloudflare R2 offers fastest instant streaming
    for item in streams:
        url = item.get("url", "")
        if "cloudflarestorage.com" in url or "r2.dev" in url:
            return item
    # 2. HubCloud 10Gbps server
    for item in streams:
        url = item.get("url", "")
        if "gpdl.hubcloud" in url:
            return item
    # 3. PixelDrain / Workers CDN
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
    filtered = buttons
    if target_ep is not None:
        single_eps = [b for b in buttons if not _is_pack(b.get("text", "")) and not _is_pack(b.get("file_title", ""))]
        if single_eps:
            filtered = single_eps

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

        label = button.get("file_title") or button.get("text") or ""
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

    # Sort highest quality/bitrate first (4K UHD DV HDR -> 1080p HEVC -> etc.)
    candidates.sort(key=lambda c: c["rank"], reverse=True)
    return candidates[:MAX_CANDIDATES]


# ------------------------------------------------------------------
# Resolve Final Playable URL
# ------------------------------------------------------------------
async def resolve_playable_url(candidate: Dict[str, Any]) -> Optional[str]:
    raw_url = candidate.get("raw_url", "")
    if not raw_url:
        return None

    # Direct CDN stream check
    if any(k in raw_url for k in ("r2.cloudflarestorage.com", "r2.dev", "gpdl.hubcloud", "workers.dev")):
        return raw_url

    # 1. HubDrive -> Resolve to HubCloud or direct link
    if "hubdrive." in raw_url:
        hc_url = await resolve_hubdrive(raw_url)
        if hc_url:
            raw_url = hc_url

    # 2. HubCloud -> GamerXYT -> Direct CDN
    if "hubcloud." in raw_url or "gamerxyt." in raw_url:
        streams = await resolve_direct_stream_links(raw_url)
        best = pick_best_stream(streams)
        if best:
            return best.get("url")

    # 3. Check if raw_url is already playable
    if raw_url.startswith("http"):
        return raw_url

    return None


async def resolve_candidate(candidate: Dict[str, Any]) -> Optional[str]:
    raw_url = candidate.get("raw_url", "")
    post_url = candidate.get("post_url", "")
    target_ep = candidate.get("episode", 1)

    key = f"fourkhd_resolved:{raw_url}:{post_url}:{target_ep}"
    return await cached_call(
        key,
        lambda: resolve_playable_url(candidate),
        ttl=STREAM_CACHE_TTL,
        negative_ttl=NEGATIVE_TTL,
    )


# ------------------------------------------------------------------
# Background Warmer
# ------------------------------------------------------------------
def warm_candidates(candidates: List[Dict[str, Any]], count: int = WARM_CANDIDATES) -> None:
    if not candidates:
        return
    for c in candidates[:count]:
        asyncio.create_task(resolve_candidate(c))
