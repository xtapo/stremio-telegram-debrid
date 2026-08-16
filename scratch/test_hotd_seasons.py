import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import httpx
import asyncio
from bs4 import BeautifulSoup
from moviesdrive_router import resolve_all_download_buttons_from_post, resolve_archive_page_episodes

async def test_hotd_seasons():
    post_url = "https://new2.moviesdrive.christmas/house-of-the-dragon-season-1-3/"
    print(f"Fetching download buttons for HOTD...")
    buttons = await resolve_all_download_buttons_from_post(post_url)
    print(f"Found {len(buttons)} buttons:")
    for b in buttons:
        print(f" - [{b['text']}] => {b['url']}")
        
    # Let's inspect one archive page
    archive_url = buttons[0]['url']
    print(f"\nInspecting archive page: {archive_url}")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(archive_url)
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.find_all('a', href=True)
        print(f"Found {len(links)} links on archive page:")
        for a in links:
            txt = a.get_text(strip=True)
            href = a['href']
            if 'hubcloud' in href or 'drive' in href or 'episode' in txt.lower() or 'ep' in txt.lower():
                print(f"   -> [{txt}] => {href}")

if __name__ == '__main__':
    asyncio.run(test_hotd_seasons())
