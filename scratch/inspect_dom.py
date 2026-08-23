import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import uhdmovies_perf as perf
from bs4 import BeautifulSoup

async def inspect_dom():
    url = 'https://uhdmovies.autos/download-somebody-2025-dual-audio-hindi-english-1080p-x264-hevc-web-dl-esubs/'
    html = await perf.fetch_text(url)
    soup = BeautifulSoup(html, 'html.parser')
    content = soup.select_one('.entry-content')
    for el in content.children:
        if el.name:
            print(f"<{el.name}>: {el.get_text(' ', strip=True)[:120]}")
            links = el.find_all('a', href=True)
            for a in links:
                print(f"   <a>: txt={a.get_text(strip=True)!r} | href={a['href'][:80]}")

asyncio.run(inspect_dom())
