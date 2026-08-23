import asyncio
import os
import sys
import re
from typing import List, Dict, Any, Optional
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import uhdmovies_perf as perf
import uhdmovies_catalog as catalog
from bs4 import BeautifulSoup

SKIP_BTN_EXACT = {
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

def parse_post_candidates_perfect(html: str, target_episode: Optional[int] = None) -> List[Dict[str, Any]]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one(".entry-content, article, div.content")
    if not content:
        return []

    candidates: List[Dict[str, Any]] = []
    seen_urls = set()

    current_season = 1
    current_heading = ""
    current_desc = ""

    for el in content.find_all(["p", "h1", "h2", "h3", "h4", "h5", "div", "span"]):
        # Check season definition
        text = el.get_text(" ", strip=True)
        if not text:
            continue

        season_match = re.search(r"Season\s*(\d+)", text, re.I)
        if season_match and ("season" in text.lower() or "episode" in text.lower()):
            current_season = int(season_match.group(1))

        if el.name in ["h1", "h2", "h3", "h4", "h5"]:
            if "here you can download" not in text.lower() and "how to download" not in text.lower():
                current_heading = text

        # Check line descriptions (e.g. "Somebody.2025.1080p... [ 6.47 GB ]")
        if el.name in ["p", "div", "span"] and not el.find("a", href=True):
            if any(q in text.lower() for q in ["2160p", "1080p", "720p", "480p", "4k", "hevc", "bluray", "web-dl", ".mkv", ".mp4"]) and any(s in text for s in ["GB", "MB", "gb", "mb", "[", "]"]):
                if "here you can download" not in text.lower():
                    current_desc = text

        # Check if direct link button
        if el.name == "a" and el.get("href"):
            links = [el]
        else:
            links = el.find_all("a", href=True)

        for a in links:
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

            # Must be a maxbutton or download link
            is_dl = (
                any("maxbutton" in c for c in a_class)
                or any(w in a_lower for w in ["download", "episode", "ep", "zip", "pack", "g-drive"])
                or ("unblockedgames" in href and any(w in a_lower for w in ["download", "episode", "ep", "zip", "pack", "g-drive"]))
            )
            if not is_dl:
                continue

            # Episode detection
            ep_match = re.search(r"(?:Episode|Ep\.?|E)\s*(\d+)", a_text, re.I)
            ep_num = int(ep_match.group(1)) if ep_match else None

            # Skip ZIP / pack if looking for specific episode
            is_pack = any(p in a_lower for p in ["zip", "pack", "complete", "rar"])
            if is_pack and target_episode is not None:
                continue
            if target_episode is not None and ep_num is not None:
                if ep_num != target_episode:
                    continue

            # Build rich title & size
            full_desc = current_desc or current_heading or a_text
            size = parse_file_size(current_desc) or parse_file_size(text) or parse_file_size(a_text)
            badge = parse_quality_badge(full_desc)

            seen_urls.add(href)
            candidates.append({
                "raw_url": href,
                "badge": badge,
                "title": full_desc,
                "btn_text": a_text,
                "size": size,
                "season": current_season,
                "episode": ep_num,
                "rank": quality_rank(full_desc),
            })


    candidates.sort(key=lambda c: c["rank"], reverse=True)
    return candidates

async def main():
    movies = await catalog.get_category_page('movies', page=1)
    series = await catalog.get_category_page('tv-series', page=1)
    hdr_movies = await catalog.get_category_page('4k-hdr', page=1)
    
    test_set = [movies[0], hdr_movies[0], series[0]]
    for item in test_set:
        print("\n" + "="*60)
        print("TESTING:", item['name'], item['url'])
        html = await perf.fetch_text(item['url'])
        cands = parse_post_candidates_perfect(html)
        print(f"Candidates found: {len(cands)}")
        for i, c in enumerate(cands[:6]):
            print(f"  [{i}] btn={c['btn_text']!r} | badge={c['badge']} | size={c['size']} | ep={c['episode']} | rank={c['rank']} | desc={c['title'][:70]}")

asyncio.run(main())
