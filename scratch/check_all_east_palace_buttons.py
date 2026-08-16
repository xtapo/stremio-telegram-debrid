import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import httpx
import asyncio
from bs4 import BeautifulSoup
from moviesdrive_router import resolve_all_download_buttons_from_post

async def check_all_archives():
    url = "https://new2.moviesdrive.christmas/the-east-palace-season-1-2026/"
    buttons = await resolve_all_download_buttons_from_post(url)
    print(f"Found {len(buttons)} download buttons on East Palace:")
    for b in buttons:
        print(f" - [{b['text']}] -> {b['url']}")

if __name__ == '__main__':
    asyncio.run(check_all_archives())
