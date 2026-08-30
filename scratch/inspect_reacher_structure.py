import asyncio
import os
import sys
import re
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import moviesdrive_resolver as resolver
import moviesdrive_perf as perf

async def inspect_page_structure():
    post_url = "https://new3.moviesdrive.christmas/reacher-season-1-4/"
    html = await resolver.fetch_html(post_url)
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup.find("div", class_=lambda c: c and "content" in c) or soup.body
    
    # Print all tags that either have Season in text or have links with 'archive' or 'hubcloud'
    tags = main.find_all(["h3", "h4", "h5", "h6", "p", "hr"])
    current_season = None
    for tag in tags:
        text = tag.get_text(" ", strip=True)
        # Check season heading
        s_m = re.search(r"\bseason\s*(\d+)\b", text, re.I)
        if s_m and ("season" in text.lower() and len(text) < 120):
            current_season = int(s_m.group(1))
            print(f"\n>>> FOUND HEADING: Season {current_season} -> {text}")
        
        links = tag.find_all("a", href=True)
        for a in links:
            href = a["href"]
            if any(k in href for k in ["archive", "mdrive.", "hubcloud"]):
                print(f"    Link: {a.get_text(strip=True)} -> {href} (Season: {current_season})")

    await perf.aclose_client()

if __name__ == "__main__":
    asyncio.run(inspect_page_structure())
