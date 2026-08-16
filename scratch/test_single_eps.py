import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import httpx
import asyncio
from bs4 import BeautifulSoup
from moviesdrive_router import resolve_archive_page_episodes, resolve_direct_stream_links

async def test_single_episodes_only():
    # Single episode archives for East Palace:
    archives = [
        {"quality": "480p", "url": "https://mdrive.lol/archive/12995/"},
        {"quality": "720p HD", "url": "https://mdrive.lol/archive/12988/"},
        {"quality": "1080p FHD", "url": "https://mdrive.lol/archive/12999/"},
        {"quality": "4K UHD", "url": "https://mdrive.lol/archive/13153/"},
    ]
    
    post_url = "https://new2.moviesdrive.christmas/the-east-palace-season-1-2026/"
    
    for arc in archives:
        print(f"\nResolving Ep 1 for {arc['quality']}:")
        hc_link = await resolve_archive_page_episodes(arc['url'], post_url, episode_num=1)
        print(f" -> HubCloud link: {hc_link}")
        if hc_link:
            direct_streams = await resolve_direct_stream_links(hc_link)
            for ds in direct_streams:
                print(f"    -> [{ds['type']}] => {ds['url'][:80]}...")
                
                # Test downloading first 100 bytes
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                    try:
                        r = await client.get(ds['url'], headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Range': 'bytes=0-100'})
                        print(f"       Status: {r.status_code}, Type: {r.headers.get('content-type')}, Range: {r.headers.get('content-range')}")
                        if r.status_code == 206 and r.content.startswith(b"\x1a\x45\xdf\xa3"):
                            print("       >>> REAL PLAYABLE VIDEO (MKV)! <<<")
                    except Exception as e:
                        print(f"       Error: {e}")

if __name__ == '__main__':
    asyncio.run(test_single_episodes_only())
