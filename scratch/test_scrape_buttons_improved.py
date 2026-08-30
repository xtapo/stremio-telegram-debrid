import asyncio
import os
import sys
import re
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import moviesdrive_resolver as resolver
import moviesdrive_perf as perf

def test_scrape_buttons_improved(html_content: str):
    soup = resolver.post_content(html_content)
    results = []
    seen = set()
    current_season = None

    # Find all elements in document order
    for elem in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "hr"]):
        # Skip container elements that contain other block elements
        if elem.find(["h1", "h2", "h3", "h4", "h5", "h6", "p", "hr"]):
            continue
            
        text = elem.get_text(" ", strip=True)
        if not text and not elem.find_all("a", href=True):
            continue

        # Check if this element is a Season heading
        # First ignore range patterns like "Season 1 - 4" or "Season 1 – 2"
        is_range = bool(re.search(r"\bseason\s*\d+\s*(?:[-–—]|to)\s*\d+\b", text, re.I))
        if not is_range and len(text) < 200:
            s_match = re.search(r"\bseason\s*(\d+)\b", text, re.I) or re.search(r"\b\[?\s*S(\d+)\s*\]?\b", text, re.I)
            if s_match:
                current_season = int(s_match.group(1))

        # Check buttons in this element
        for a in elem.find_all("a", href=True):
            href = a["href"]
            if href in seen:
                continue
            btn_text = a.get_text(strip=True)
            if not any(host in href for host in resolver.BUTTON_HOSTS):
                continue
            if any(word in href.lower() for word in ("category", "tag", "telegram", "join")):
                continue

            btn_season = current_season
            # Explicit season in button text overrides section season
            bs_match = re.search(r"\bseason\s*(\d+)\b|\bS(\d+)\b", btn_text, re.I)
            if bs_match and not re.search(r"\bseason\s*\d+\s*(?:[-–—]|to)\s*\d+\b", btn_text, re.I):
                btn_season = int(bs_match.group(1) or bs_match.group(2))

            seen.add(href)
            results.append({"text": btn_text, "url": href, "season": btn_season, "heading_text": text})

    return results

async def main():
    with open("scratch/reacher_post.html", "r", encoding="utf-8") as f:
        html = f.read()

    buttons = test_scrape_buttons_improved(html)
    print(f"Total buttons found: {len(buttons)}")
    
    seasons = {}
    for b in buttons:
        s = b['season']
        seasons.setdefault(s, []).append(b)

    for s, btns in sorted(seasons.items(), key=lambda x: (x[0] is None, x[0])):
        print(f"\n=== Season {s} ({len(btns)} buttons) ===")
        for b in btns:
            print(f"  [{b['text']}] -> {b['url']}")

    await perf.aclose_client()

if __name__ == "__main__":
    asyncio.run(main())
