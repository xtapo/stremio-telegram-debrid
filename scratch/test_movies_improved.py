import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.stdout.reconfigure(encoding='utf-8')
import httpx
import asyncio
from bs4 import BeautifulSoup
import urllib.parse
import re
from test_improved_resolver import resolve_direct_stream_links_improved
from moviesdrive_router import resolve_all_download_buttons_from_post, resolve_hubcloud_files_from_url

async def test_movies():
    print("Testing Inception Movie:")
    buttons = await resolve_all_download_buttons_from_post("https://new2.moviesdrive.christmas/inception-2010/")
    if buttons:
        files = await resolve_hubcloud_files_from_url(buttons[0]['url'])
        if files:
            s = await resolve_direct_stream_links_improved(files[0]['url'])
            for item in s:
                print(f" -> [{item['type']}] => {item['url'][:100]}...")

    print("\nTesting Deadpool Movie:")
    buttons_dp = await resolve_all_download_buttons_from_post("https://new2.moviesdrive.christmas/deadpool-wolverine-2024/")
    if buttons_dp:
        files_dp = await resolve_hubcloud_files_from_url(buttons_dp[0]['url'])
        if files_dp:
            s_dp = await resolve_direct_stream_links_improved(files_dp[0]['url'])
            for item in s_dp:
                print(f" -> [{item['type']}] => {item['url'][:100]}...")

if __name__ == '__main__':
    asyncio.run(test_movies())
