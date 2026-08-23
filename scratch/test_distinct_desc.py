import asyncio
import os
import sys
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import uhdmovies_perf as perf
import uhdmovies_resolver as resolver
from bs4 import BeautifulSoup

SKIP_BTN_EXACT = {
    "hevc", "1080p uhd", "uhdmovies", "moviesmod", "4k", "2160phevc",
    "1080p x264 uhd", "1080p 60fps", "1080p x265 10bit", "4k hdr", "4k 2160p",
    "3d movies", "about us", "contact", "privacy policy", "terms", "trailer",
    "join our group", "request a movie", "home", "admin d", "view all posts",
    "term & conditions", "cookie policy (uk)"
}

def parse_post_candidates_v3(html: str, target_episode: int = None):
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one(".entry-content, article, div.content")
    if not content:
        return []

    candidates = []
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

        if any(base in href for base in perf.UHDMOVIES_BACKUP_URLS) and not "/?sid=" in href:
            continue

        # Find preceding description (looking backwards from 'a')
        prev_desc = ""
        curr = a.parent
        for _ in range(5):
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
        size = resolver.parse_file_size(full_desc) or resolver.parse_file_size(a_text)
        badge = resolver.parse_quality_badge(full_desc)

        seen_urls.add(href)
        candidates.append({
            "raw_url": href,
            "badge": badge,
            "title": full_desc,
            "btn_text": a_text,
            "size": size,
            "episode": ep_num,
            "rank": resolver.quality_rank(full_desc),
        })

    candidates.sort(key=lambda c: c["rank"], reverse=True)
    return candidates

async def main():
    url = "https://uhdmovies.autos/download-somebody-2025-dual-audio-hindi-english-1080p-x264-hevc-web-dl-esubs/"
    html = await perf.fetch_text(url)
    cands = parse_post_candidates_v3(html)
    print(f"Candidates found: {len(cands)}")
    for c in cands:
        print(f"  badge={c['badge']} | size={c['size']} | rank={c['rank']} | desc={c['title']}")

asyncio.run(main())
