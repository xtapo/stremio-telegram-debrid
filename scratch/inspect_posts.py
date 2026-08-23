import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
import asyncio, re, urllib.parse, httpx
from bs4 import BeautifulSoup
from uhdmovies_catalog import search_uhdmovies
from uhdmovies_resolver import get_post_page

async def inspect_posts():
    items = await search_uhdmovies("Avatar")
    print(f"Found {len(items)} items for Avatar")
    for item in items[:2]:
        print(f"\n--- Post: {item['name']} ({item['url']}) ---")
        html = await get_post_page(item["url"])
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select(".entry-content a[href]"):
            href = a["href"]
            if any(k in href for k in ["unblocked", "sid=", "driveseed", "hubcloud", "drive"]):
                print(f"  Link [{a.get_text(strip=True)[:30]}]: {href[:90]}")

asyncio.run(inspect_posts())
