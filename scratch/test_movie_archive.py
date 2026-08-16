import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import httpx
import asyncio
from moviesdrive_router import resolve_archive_page_episodes, resolve_direct_stream_links

async def test_movie_archive():
    # Minions archive buttons:
    archive_url = "https://mdrive.lol/archive/15626/"
    post_url = "https://new2.moviesdrive.christmas/minions-monsters-2026-web-dl-hindi-dd5-1-english-480p-720p-1080p-2160p-4k-sdr-x264-esubs-full-movie/"
    
    print(f"Resolving movie archive {archive_url} with episode_num=1...")
    hc_link = await resolve_archive_page_episodes(archive_url, post_url, episode_num=1)
    print(f"HubCloud Link: {hc_link}")
    
    if hc_link:
        direct = await resolve_direct_stream_links(hc_link)
        print("Direct streams:", direct)

if __name__ == '__main__':
    asyncio.run(test_movie_archive())
