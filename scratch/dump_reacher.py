import asyncio
import os
import sys
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import moviesdrive_resolver as resolver
import moviesdrive_perf as perf

async def dump_reacher():
    post_url = "https://new3.moviesdrive.christmas/reacher-season-1-4/"
    html = await resolver.fetch_html(post_url)
    soup = BeautifulSoup(html, "html.parser")
    content = resolver.post_content(html)
    
    for i, elem in enumerate(content.children):
        if elem.name:
            t = elem.get_text(" ", strip=True)
            links = [a['href'] for a in elem.find_all('a', href=True) if 'archive' in a['href']]
            print(f"[{elem.name}] text: {t[:80]}... | archive_links: {len(links)}")
            if links:
                print("   Link sample:", links[0])

    await perf.aclose_client()

if __name__ == "__main__":
    asyncio.run(dump_reacher())
