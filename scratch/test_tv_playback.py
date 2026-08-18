import httpx
import json
import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
from ernax_router import get_ernax_seed, fetch_ernax_stream_sources

async def test_tv_playback():
    tmdb_id = 1396
    seed = await get_ernax_seed(tmdb_id)
    print("Seed:", seed)
    
    data = await fetch_ernax_stream_sources(
        tmdb_id=tmdb_id,
        media_type="tv",
        title="Breaking Bad",
        year="2008",
        season=1,
        episode=1,
        imdb_id="tt0903747",
        seed=seed
    )
    
    first_url = data['sources'][0]['url']
    print("TV First URL:", first_url)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.vidking.net/",
        "Origin": "https://www.vidking.net"
    }
    
    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        res = await client.get(first_url)
        print("TV m3u8 status:", res.status_code, "length:", len(res.content))
        lines = [l.strip() for l in res.text.splitlines() if l.strip() and not l.startswith("#")]
        if lines:
            seg = lines[0]
            print("Fetching TV segment:", seg)
            r_seg = await client.get(seg)
            print("TV segment status:", r_seg.status_code, "bytes:", len(r_seg.content))

if __name__ == "__main__":
    asyncio.run(test_tv_playback())
