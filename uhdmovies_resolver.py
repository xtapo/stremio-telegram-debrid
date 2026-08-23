"""
Link resolving layer for UHDMovies addon.

A UHDMovies lookup chain:
    post page -> [cloud.unblockedgames.world / driveseed / hubcloud] -> direct CDN stream (Google User Content / CDN)

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

import httpx
from bs4 import BeautifulSoup, SoupStrainer

import uhdmovies_perf as perf
from uhdmovies_perf import (
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

logger = logging.getLogger("uhdmovies_addon")

POST_TTL = perf._env_int("UHD_POST_TTL", 900)
POST_STALE_TTL = perf._env_int("UHD_POST_STALE_TTL", 3600)
MAX_CANDIDATES = perf._env_int("UHD_MAX_CANDIDATES", 12)
WARM_CANDIDATES = perf._env_int("UHD_WARM_CANDIDATES", 2)

SKIP_WORDS = (
    "category", "tag", "contact", "dmca", "privacy", "how-to-download",
    "disclaimer", "join-our-group", "request-a-movie", "whatsapp", "telegram",
    "catimages", "sharethis", "google", "facebook", "twitter", "comment", "trailer",
)
PACK_WORDS = ("zip", "pack", "complete", "season zip", "rar")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def current_base() -> str:
    return get_active_base(perf.UHDMOVIES_BASE_DEFAULT).rstrip("/")


def absolute(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http"):
        full = url
    else:
        full = urllib.parse.urljoin(current_base() + "/", url.lstrip("/"))
    if not full.endswith("/") and not any(ext in full for ext in (".json", ".html", ".php", "?", "#")):
        full += "/"
    return full


def strip_base(url: str) -> str:
    out = url or ""
    for base in perf.UHDMOVIES_BACKUP_URLS:
        out = out.replace(base, "")
    return out.strip("/")


def parse_quality_badge(title: str) -> str:
    t = (title or "").lower()
    badges = []
    if "2160p" in t or "4k" in t:
        badges.append("4K UHD")
    elif "1080p" in t:
        badges.append("1080p FHD")
    elif "720p" in t:
        badges.append("720p HD")
    elif "480p" in t:
        badges.append("480p SD")

    if "dovi" in t or "dv" in t or "dolby vision" in t:
        badges.append("DV")
    if "hdr10+" in t:
        badges.append("HDR10+")
    elif "hdr" in t:
        badges.append("HDR")
    if "remux" in t:
        badges.append("REMUX")
    if "60fps" in t:
        badges.append("60FPS")
    if "10bit" in t:
        badges.append("10Bit")
    if "hevc" in t or "x265" in t or "h.265" in t:
        badges.append("HEVC")

    return " | ".join(badges) if badges else "HD"


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

    if "dovi" in t or "dv" in t:
        rank += 50
    if "hdr" in t:
        rank += 40
    if "remux" in t:
        rank += 35
    if "60fps" in t:
        rank += 30
    if "10bit" in t:
        rank += 20
    if "hevc" in t or "x265" in t:
        rank += 15
    if "dual audio" in t or "hindi" in t or "english" in t:
        rank += 5
    return rank


def parse_file_size(text: str) -> str:
    m = re.search(r"(\d+(?:\.\d+)?\s*(?:GB|MB))", text or "", re.I)
    return m.group(1).upper() if m else ""


# ------------------------------------------------------------------
# Level 1: UHDMovies Post Scraping
# ------------------------------------------------------------------
async def fetch_html(url: str, race: bool = True) -> Optional[str]:
    if not url:
        return None
    headers = {"Referer": current_base() + "/"}
    if race and base_of(url, perf.UHDMOVIES_BACKUP_URLS):
        candidates = mirror_candidates(url, perf.UHDMOVIES_BACKUP_URLS, perf.UHDMOVIES_BASE_DEFAULT)
        text, final_url = await race_fetch_text(candidates, headers=headers)
        if text and final_url:
            winner = base_of(final_url, perf.UHDMOVIES_BACKUP_URLS)
            if winner:
                note_active_base(winner)
        return text
    return await fetch_text(url, headers=headers)


async def get_post_page(url: str) -> Optional[str]:
    clean_url = absolute(url)
    key = f"uhd:post:{strip_base(clean_url)}"

    async def _fetch():
        return await fetch_html(clean_url, race=True)

    return await cached_call(
        key,
        _fetch,
        ttl=POST_TTL,
        stale_ttl=POST_STALE_TTL,
        negative_ttl=NEGATIVE_TTL,
    )


SKIP_BTN_EXACT = {
    "hevc", "1080p uhd", "uhdmovies", "moviesmod", "4k", "2160phevc",
    "1080p x264 uhd", "1080p 60fps", "1080p x265 10bit", "4k hdr", "4k 2160p",
    "3d movies", "about us", "contact", "privacy policy", "terms", "trailer",
    "join our group", "request a movie", "home", "admin d", "view all posts",
    "term & conditions", "cookie policy (uk)"
}


def parse_post_candidates(html: str, target_episode: Optional[int] = None) -> List[Dict[str, Any]]:
    """Parse UHDMovies post HTML and return candidate stream list."""
    if not html:
        return []

    soup = make_soup(html)
    content = soup.select_one(".entry-content, article, div.content")
    if not content:
        return []

    candidates: List[Dict[str, Any]] = []
    seen_urls = set()

    for a in content.select("a[href]"):
        href = a["href"].strip()
        a_text = a.get_text(strip=True)
        a_lower = a_text.lower()
        a_class = a.get("class") or []

        if not href or href.startswith("#") or href in seen_urls:
            continue
        if a_lower in SKIP_BTN_EXACT:
            continue
        if any(w in href.lower() for w in ["moviesmod.org", "category", "tag", "contact", "dmca", "privacy", "facebook", "twitter", "telegram", "whatsapp"]):
            continue

        is_dl = (
            any("maxbutton" in c for c in a_class)
            or any(w in a_lower for w in ["download", "episode", "ep", "zip", "pack", "g-drive"])
            or ("unblockedgames" in href and any(w in a_lower for w in ["download", "episode", "ep", "zip", "pack", "g-drive"]))
            or "driveseed" in href
            or "hubcloud" in href
            or "/?sid=" in href
        )
        if not is_dl:
            continue

        # Ignore internal site links without ?sid=
        if any(base in href for base in perf.UHDMOVIES_BACKUP_URLS) and not "/?sid=" in href:
            continue

        # Find preceding description (looking backwards from 'a')
        prev_desc = ""
        curr = a.parent
        for _ in range(6):
            if not curr:
                break
            prev = curr.find_previous(["p", "h1", "h2", "h3", "h4", "h5", "strong"])
            if prev:
                prev_text = prev.get_text(" ", strip=True)
                if any(q in prev_text.lower() for q in ["2160p", "1080p", "720p", "480p", "4k", "hevc", "bluray", "web-dl", ".mkv", ".mp4"]) and not "here you can download" in prev_text.lower():
                    prev_desc = prev_text
                    break
            curr = curr.parent

        ep_match = re.search(r"(?:Episode|Ep\.?|E)\s*(\d+)", a_text, re.I)
        ep_num = int(ep_match.group(1)) if ep_match else None

        is_pack = any(p in a_lower for p in ["zip", "pack", "complete", "rar"])
        if is_pack and target_episode is not None:
            continue
        if target_episode is not None and ep_num is not None:
            if ep_num != target_episode:
                continue

        full_desc = prev_desc or a_text
        size = parse_file_size(full_desc) or parse_file_size(a_text)
        badge = parse_quality_badge(full_desc)

        seen_urls.add(href)
        candidates.append({
            "raw_url": href,
            "badge": badge,
            "title": full_desc,
            "btn_text": a_text,
            "size": size,
            "season": 1,
            "episode": ep_num,
            "rank": quality_rank(full_desc),
        })

    candidates.sort(key=lambda c: c["rank"], reverse=True)
    return candidates[:MAX_CANDIDATES]



async def collect_candidates(
    post_url: str, episode: Optional[int] = None
) -> List[Dict[str, Any]]:
    html = await get_post_page(post_url)
    if not html:
        return []
    cands = parse_post_candidates(html, target_episode=episode)
    for c in cands:
        c["post_url"] = post_url
    return cands


# ------------------------------------------------------------------
# Level 2: UnblockedGames & DriveSeed Resolver Chain
# ------------------------------------------------------------------
async def resolve_unblocked_link(url: str, timeout: float = 20.0) -> Optional[str]:
    """
    Bypasses cloud.unblockedgames.world / driveseed.org resolver chain
    and returns direct video streaming URL (Cloudflare Workers / direct CDN).
    """
    if not url:
        return None

    # Check if already a direct streamable file
    if any(url.endswith(ext) for ext in (".mkv", ".mp4", ".m4v", ".webm")):
        return url
    if any(k in url for k in ("googleusercontent.com", "r2.dev", "cloudflarestorage.com", "workers.dev")):
        return url

    headers = {
        "User-Agent": perf.USER_AGENT,
        "Referer": current_base() + "/",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        client = await perf.get_client()

        # Step 1: GET landing
        r1 = await client.get(url, headers=headers, timeout=timeout)
        if not r1.text:
            return None

        soup1 = make_soup(r1.text)
        form1 = soup1.select_one("form")
        if not form1:
            if any(k in str(r1.url) for k in ("googleusercontent.com", "cdn", "workers.dev", ".mkv", ".mp4")):
                return str(r1.url)
            return None

        action1 = form1.get("action") or url
        data1 = {inp.get("name"): inp.get("value", "") for inp in form1.select("input") if inp.get("name")}

        # Step 2: POST form 1
        r2 = await client.post(action1, data=data1, headers={"Referer": url}, timeout=timeout)
        soup2 = make_soup(r2.text)
        form2 = soup2.select_one("form")
        if not form2:
            return None

        action2 = form2.get("action") or str(r2.url)
        data2 = {inp.get("name"): inp.get("value", "") for inp in form2.select("input") if inp.get("name")}

        # Step 3: POST form 2
        r3 = await client.post(action2, data=data2, headers={"Referer": str(r2.url)}, timeout=timeout)

        # Step 4: Extract dynamic cookie & go parameter
        match_cookie = re.search(r"s_\d+\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", r3.text)
        match_go = re.search(r"https?://[^'\"\s]+/\?go=([^'\"\s]+)", r3.text)

        if not match_cookie or not match_go:
            return None

        c_name, c_val = match_cookie.groups()
        go_param = match_go.group(1)
        base_domain = urllib.parse.urlsplit(str(r3.url)).netloc
        go_url = f"https://{base_domain}/?go={go_param}"

        client.cookies.set(c_name, c_val, domain=base_domain)

        # Step 5: GET go_url -> check meta refresh or window.location
        r4 = await client.get(go_url, headers={"Referer": str(r3.url)}, timeout=timeout)

        target_url = None
        meta_refresh = re.search(r'content=["\']\d+;\s*url=([^"\']+)["\']', r4.text, re.I)
        if meta_refresh:
            target_url = meta_refresh.group(1)
        else:
            loc_match = re.search(r'window\.location\.(?:replace|href)\s*=\s*["\']([^"\']+)["\']', r4.text)
            if loc_match:
                target_url = loc_match.group(1)

        if not target_url:
            return None

        # Step 6: Follow target URL (e.g. driveseed.org/r?key=...)
        r5 = await client.get(target_url, headers={"Referer": str(r4.url)}, timeout=timeout)
        file_match = re.search(r'window\.location\.replace\(["\']([^"\']+)["\']\)', r5.text)
        if file_match:
            rel = file_match.group(1)
            driveseed_file_url = urllib.parse.urljoin(str(r5.url), rel)
        else:
            driveseed_file_url = str(r5.url)

        # Step 7: On driveseed file page, extract direct video / Resume Cloud (/zfile/) link
        r6 = await client.get(driveseed_file_url, headers={"Referer": str(r5.url)}, timeout=timeout)
        soup6 = make_soup(r6.text)

        zfile_url = None
        instant_download_url = None
        for a in soup6.select("a[href]"):
            href = a.get("href")
            btn_text = a.get_text(strip=True).lower()
            if not href or "login" in href.lower() or href.startswith("#"):
                continue
            if "/zfile/" in href or "resume cloud" in btn_text:
                zfile_url = urllib.parse.urljoin(str(r6.url), href)
                break
            if "instant download" in btn_text or "direct download" in btn_text:
                instant_download_url = href

        # If /zfile/ is present, follow it to get the direct Cloudflare Workers / CDN stream link
        if zfile_url:
            r_z = await client.get(zfile_url, headers={"Referer": driveseed_file_url}, timeout=timeout)
            soup_z = make_soup(r_z.text)
            for a in soup_z.select("a[href]"):
                h = a.get("href")
                t = a.get_text(strip=True).lower()
                if (
                    "cloud resume download" in t
                    or "workers.dev" in h
                    or any(h.endswith(ext) or ext in h for ext in (".mkv", ".mp4", ".m4v"))
                    or "googleusercontent" in h
                ):
                    return h

        # Fallback to instant download URL resolution
        if instant_download_url:
            if any(k in instant_download_url for k in ("googleusercontent.com", "workers.dev", "r2.dev")):
                return instant_download_url
            try:
                r_head = await client.head(
                    instant_download_url,
                    headers={"Referer": driveseed_file_url},
                    timeout=10.0,
                )
                loc = r_head.headers.get("location", "")
                if loc:
                    if "url=" in loc:
                        parsed_loc = urllib.parse.urlsplit(loc)
                        q = urllib.parse.parse_qs(parsed_loc.query)
                        real_video_url = q.get("url", [None])[0]
                        if real_video_url and real_video_url.startswith("http"):
                            return real_video_url
                    if loc.startswith("http"):
                        return loc
            except Exception:
                pass
            return instant_download_url

        return None

    except Exception as e:
        logger.debug(f"resolve_unblocked_link failed for {url}: {e}")
        return None


# ------------------------------------------------------------------
# Level 3: Playable Stream URL Resolver & Caching
# ------------------------------------------------------------------
async def resolve_candidate(candidate: Dict[str, Any]) -> Optional[str]:
    raw_url = candidate.get("raw_url") or ""
    if not raw_url:
        return None

    # Check cache
    cache_key = f"uhd:stream:{raw_url}"
    cached_val, hit = perf.get_cached(cache_key)
    if hit and cached_val:
        return cached_val

    resolved = None
    if "unblockedgames" in raw_url or "driveseed" in raw_url or "/?sid=" in raw_url:
        resolved = await resolve_unblocked_link(raw_url)
    elif "hubcloud" in raw_url:
        try:
            import hdhub4u_resolver
            resolved = await hdhub4u_resolver.resolve_hubcloud_page(raw_url)
        except Exception:
            resolved = None
    elif any(raw_url.endswith(ext) for ext in (".mkv", ".mp4", ".m4v", ".webm")) or any(
        k in raw_url for k in ("workers.dev", "googleusercontent.com", "r2.dev", "cloudflarestorage.com")
    ):
        resolved = raw_url

    if resolved and resolved.startswith("http"):
        perf.set_cached(cache_key, resolved, ttl=STREAM_CACHE_TTL)
        return resolved

    return None

