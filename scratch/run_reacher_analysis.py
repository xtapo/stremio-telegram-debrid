import asyncio
import os
import sys
import re
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import moviesdrive_resolver as resolver
import moviesdrive_perf as perf

async def run():
    post_url = "https://new3.moviesdrive.christmas/reacher-season-1-4/"
    html = await resolver.fetch_html(post_url)
    with open("scratch/reacher_post.html", "w", encoding="utf-8") as f:
        f.write(html or "")
    
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup.find("div", class_=lambda c: c and "content" in c) or soup.body
    
    with open("scratch/reacher_analysis.txt", "w", encoding="utf-8") as f:
        # Traverse elements sequentially
        current_season = None
        for tag in main.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "hr"]):
            # If tag contains child block elements, skip searching its text directly to avoid outer div matching
            if tag.find(["h1", "h2", "h3", "h4", "h5", "h6", "p", "hr"]):
                continue
            text = tag.get_text(" ", strip=True)
            s_m = re.search(r"\bseason\s*(\d+)\b", text, re.I)
            if s_m and len(text) < 150:
                current_season = int(s_m.group(1))
                f.write(f"\n[SEASON HEADING {current_season}] {text}\n")
            
            for a in tag.find_all("a", href=True):
                href = a["href"]
                if any(k in href for k in ["archive", "mdrive.", "hubcloud"]):
                    f.write(f"   -> Link (Season {current_season}): {a.get_text(strip=True)} | {href}\n")

    await perf.aclose_client()

if __name__ == "__main__":
    asyncio.run(run())
