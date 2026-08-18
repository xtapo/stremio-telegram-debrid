import httpx
import json
import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
from ernax_router import get_ernax_seed, fetch_ernax_stream_sources

async def test_fresh_token():
    tmdb_id = 550
    seed = await get_ernax_seed(tmdb_id)
    print("Seed:", seed)
    
    data = await fetch_ernax_stream_sources(
        tmdb_id=tmdb_id,
        media_type="movie",
        title="Fight Club",
        year="1999",
        imdb_id="tt0137523",
        seed=seed
    )
    
    first_url = data['sources'][0]['url']
    print("Fresh URL:", first_url)
    
    # Test immediately with various referers
    for ref in [None, "", "https://ernax.pro/", "https://www.vidking.net/", "https://stream.ernax.pro/"]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        if ref is not None:
            headers["Referer"] = ref
            headers["Origin"] = ref.rstrip("/")
            
        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            res = await client.get(first_url)
            print(f"Referer={ref!r} -> Status: {res.status_code}, Length: {len(res.content)}")
            if res.status_code == 200:
                print("First 150 chars of m3u8:", res.text[:150])

if __name__ == "__main__":
    asyncio.run(test_fresh_token())
