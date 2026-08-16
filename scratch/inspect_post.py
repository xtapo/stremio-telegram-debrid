import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import httpx
import asyncio
from bs4 import BeautifulSoup

async def inspect_post_html():
    post_url = "https://new2.moviesdrive.christmas/house-of-the-dragon-season-1-3/"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(post_url)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Let's find all headers and links in order
        content = soup.find('div', class_='entry-content') or soup.body
        for elem in content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'p', 'hr']):
            text = elem.get_text(strip=True)
            links = elem.find_all('a', href=True)
            if 'season' in text.lower() or links:
                btn_info = [f"[{a.get_text(strip=True)}]({a['href']})" for a in links if 'archive' in a['href'] or 'hubcloud' in a['href'] or 'drive' in a['href']]
                if btn_info or 'season' in text.lower():
                    print(f"Elem <{elem.name}>: {text[:60]} => {btn_info}")

if __name__ == '__main__':
    asyncio.run(inspect_post_html())
