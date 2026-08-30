import asyncio
import os
import sys
import re
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import moviesdrive_resolver as resolver
import moviesdrive_perf as perf

async def inspect_reacher_html():
    post_url = "https://new3.moviesdrive.christmas/reacher-season-1-4/"
    html = await resolver.fetch_html(post_url)
    with open("scratch/reacher_post.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Saved reacher_post.html, analyzing tags...")
    
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup.find("div", class_=lambda c: c and "content" in c) or soup.body
    
    current_season = None
    for tag in main.find_all(True, recursive=False):
        pass # let's iterate children or elements
    
    for tag in main.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "hr"]):
        # only look at leaf / direct blocks
        text = tag.get_text(" ", strip=True)
        s_m = re.search(r"\bseason\s*(\d+)\b", text, re.I)
        if s_m and len(text) < 150:
            current_season = int(s_m.group(1))
            print(f"[HEADING] Season {current_season} text: {text[:60]}")
        
        # Check direct <a> children
        for a in tag.find_all("a", href=True, recursive=False):
            href = a["href"]
            if "archive" in href or "hubcloud" in href or "mdrive" in href:
                print(f"   [BUTTON] text: {a.get_text(strip=True)} -> Season: {current_season} -> {href}")

    await perf.aclose_client()

if __name__ == "__main__":
    asyncio.run(inspect_reacher_html())
