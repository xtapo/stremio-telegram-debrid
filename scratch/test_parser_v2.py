import asyncio
import os
import sys
import re
from typing import List, Dict, Any, Optional
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import uhdmovies_perf as perf
import uhdmovies_catalog as catalog
from bs4 import BeautifulSoup

SKIP_BTN_TEXTS = {
    "hevc", "1080p uhd", "uhdmovies", "moviesmod", "4k", "2160phevc",
    "1080p x264 uhd", "1080p 60fps", "1080p x265 10bit", "4k hdr", "4k 2160p",
    "3d movies", "about us", "contact", "privacy policy", "terms", "trailer",
    "join our group", "request a movie", "home", "admin d", "view all posts"
}

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

def parse_post_candidates_v2(html: str, target_episode: Optional[int] = None) -> List[Dict[str, Any]]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one(".entry-content, article, div.content")
    if not content:
        return []

    candidates: List[Dict[str, Any]] = []
    seen_urls = set()

    current_section_title = ""
    current_season = 1
    recent_line_desc = ""

    # Iterate through all direct block children or elements
    for el in content.find_all(["p", "h1", "h2", "h3", "h4", "h5", "div", "hr"]):
        text = el.get_text(" ", strip=True)
        if not text:
            continue

        # Skip the bottom generic SEO / tag / footer text
        if "here you can download" in text.lower() or "we do not host any files" in text.lower():
            continue

        # Check season definition
        season_match = re.search(r"Season\s*(\d+)", text, re.I)
        if season_match:
            current_season = int(season_match.group(1))

        # Check if heading or quality section
        if el.name in ["h1", "h2", "h3", "h4", "h5"] or any(q in text.lower() for q in ["season", "download", "web-dl", "bluray", "2160p", "1080p", "720p", "480p"]):
            if not el.find("a", href=True):
                current_section_title = text

        # Check line descriptions (e.g. "Somebody.2025.1080p... [ 6.47 GB ]")
        for ln in re.split(r"[\r\n]+", text):
            ln_s = ln.strip()
            if any(q in ln_s.lower() for q in ["2160p", "1080p", "720p", "480p", "4k", "hevc", "bluray", "web-dl", ".mkv", ".mp4"]) and not el.find("a", href=True):
                recent_line_desc = ln_s

        links = el.find_all("a", href=True)
        for a in links:
            href = a["href"].strip()
            a_text = a.get_text(strip=True)
            a_lower = a_text.lower()

            if not href or href.startswith("#") or href in seen_urls:
                continue
            if a_lower in SKIP_BTN_TEXTS:
                continue
            if any(w in href.lower() for w in ["moviesmod.org", "category", "tag", "contact", "dmca", "privacy"]):
                continue

            # Must be a valid download host or button
            is_valid_btn = (
                "download" in a_lower
                or "g-drive" in a_lower
                or "episode" in a_lower
                or "ep" in a_lower
                or "zip" in a_lower
                or "pack" in a_lower
                or "drive" in a_lower
                or "unblockedgames" in href
                or "driveseed" in href
                or "hubcloud" in href
                or "/?sid=" in href
            )
            if not is_valid_btn:
                continue

            # Ignore the category tag links even if wrapped in sid
            if a_lower in SKIP_BTN_TEXTS or any(a_lower == s for s in ["hevc", "1080p uhd", "uhdmovies"]):
                continue

            # Episode detection
            ep_match = re.search(r"(?:Episode|Ep\.?|E)\s*(\d+)", a_text, re.I)
            if not ep_match and el.name != "p":
                ep_match = re.search(r"(?:Episode|Ep\.?|E)\s*(\d+)", text, re.I)
            ep_num = int(ep_match.group(1)) if ep_match else None

            # Skip ZIP / pack if looking for specific episode
            is_pack = any(p in a_lower for p in ["zip", "pack", "complete", "rar"])
            if is_pack and target_episode is not None:
                continue
            if target_episode is not None and ep_num is not None:
                if ep_num != target_episode:
                    continue

            # Full description
            full_desc = recent_line_desc or current_section_title or a_text
            size = parse_file_size(full_desc) or parse_file_size(text) or parse_file_size(a_text)
            badge = parse_quality_badge(full_desc or text)

            seen_urls.add(href)
            candidates.append({
                "raw_url": href,
                "badge": badge,
                "title": full_desc or a_text,
                "btn_text": a_text,
                "size": size,
                "season": current_season,
                "episode": ep_num,
                "rank": quality_rank(full_desc or text),
            })

    candidates.sort(key=lambda c: c["rank"], reverse=True)
    return candidates

async def test_parser():
    movies = await catalog.get_category_page('movies', page=1)
    series = await catalog.get_category_page('tv-series', page=1)
    
    for item in movies[:2] + series[:2]:
        print("\n" + "="*50)
        print("TESTING:", item['name'])
        html = await perf.fetch_text(item['url'])
        cands = parse_post_candidates_v2(html)
        print(f"Candidates found: {len(cands)}")
        for i, c in enumerate(cands):
            print(f"  [{i}] btn={c['btn_text']!r} | badge={c['badge']} | size={c['size']} | ep={c['episode']} | title={c['title'][:60]}")

asyncio.run(test_parser())
