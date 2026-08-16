import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import asyncio
import httpx
from moviesdrive_router import resolve_hubcloud_links_from_post, resolve_hubcloud_files_from_url, resolve_direct_stream_links

async def test_spooky():
    url = "https://new2.moviesdrive.christmas/spooky-in-love-season-1-2026/"
    print("Fetching:", url)
    buttons = await resolve_hubcloud_links_from_post(url)
    print(f"Found {len(buttons)} hubcloud buttons:")
    for b in buttons:
        print(f" - [{b['text']}] => {b['url']}")
        
    for b in buttons[:4]:
        files_unfiltered = await resolve_hubcloud_files_from_url(b['url'])
        print(f"\nButton [{b['text']}] unfiltered files count: {len(files_unfiltered)}")
        for f in files_unfiltered[:5]:
            print(f"   -> {f.get('file_name')} ({f.get('size')}) => {f.get('url')}")
            
        files_filtered = await resolve_hubcloud_files_from_url(b['url'], filter_query="S01E01")
        print(f"Button [{b['text']}] filtered 'S01E01' files count: {len(files_filtered)}")
        for f in files_filtered[:5]:
            print(f"   -> {f.get('file_name')}")

if __name__ == '__main__':
    asyncio.run(test_spooky())
