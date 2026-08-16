import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import httpx
import asyncio
from bs4 import BeautifulSoup
from moviesdrive_router import resolve_all_download_buttons_from_post, resolve_hubcloud_files_from_url, resolve_direct_stream_links

async def test_minions():
    post_slug = "minions-monsters-2026-web-dl-hindi-dd5-1-english-480p-720p-1080p-2160p-4k-sdr-x264-esubs-full-movie"
    post_url = f"https://new2.moviesdrive.christmas/{post_slug}/"
    
    print(f"Fetching buttons from {post_url}...")
    buttons = await resolve_all_download_buttons_from_post(post_url)
    print(f"Found {len(buttons)} buttons:")
    for b in buttons:
        print(f" - [{b['text']}] -> {b['url']}")
        
    direct_hc_buttons = [b for b in buttons if 'hubcloud' in b['url']]
    archive_buttons = [b for b in buttons if 'archive/' in b['url'] or 'mdrive.' in b['url']]
    print(f"Direct HC buttons: {len(direct_hc_buttons)}, Archive buttons: {len(archive_buttons)}")
    
    for b in direct_hc_buttons:
        print(f"\nResolving HC files from {b['url']}...")
        files = await resolve_hubcloud_files_from_url(b['url'])
        print(f"Found {len(files)} files:")
        for f in files:
            print(f"   -> {f.get('file_name')} ({f.get('size')}) => {f.get('url')}")
            if f.get('url'):
                direct_streams = await resolve_direct_stream_links(f['url'])
                print(f"      Direct streams: {direct_streams}")

if __name__ == '__main__':
    asyncio.run(test_minions())
