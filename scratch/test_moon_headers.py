import httpx
import json
import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
from ernax_router import get_ernax_seed, fetch_ernax_stream_sources

async def test_moon():
    # 1. Fresh seed and fresh sources
    tmdb_id = 550
    seed = await get_ernax_seed(tmdb_id)
    print("Fresh Seed:", seed)
    
    stream_payload = await fetch_ernax_stream_sources(
        tmdb_id=tmdb_id,
        media_type="movie",
        title="Fight Club",
        year="1999",
        imdb_id="tt0137523",
        seed=seed
    )
    print("Payload:", json.dumps(stream_payload, indent=2))
    
    master_url = stream_payload.get("playlist")
    sources = stream_payload.get("sources", [])
    
    print("\nTesting Master URL:", master_url)
    
    # Test multiple header combinations
    test_headers = [
        {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"},
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://ernax.pro/",
            "Origin": "https://ernax.pro"
        },
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://speedracelight.com/",
            "Origin": "https://speedracelight.com"
        },
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://stream.ernax.pro/",
            "Origin": "https://stream.ernax.pro"
        }
    ]
    
    for h in test_headers:
        print(f"\n--- Testing with headers: {h} ---")
        try:
            async with httpx.AsyncClient(headers=h, follow_redirects=True, timeout=10.0) as client:
                res = await client.get(master_url)
                print(f"Status: {res.status_code}, Content-Type: {res.headers.get('content-type')}")
                print(f"Body (first 200 chars): {res.text[:200]}")
        except Exception as e:
            print(f"Error: {e}")
            
    # Also test first source url
    if sources:
        first_src = sources[0].get("url")
        print("\nTesting First Source URL:", first_src)
        for h in test_headers:
            print(f"\n--- Testing source with headers: {h} ---")
            try:
                async with httpx.AsyncClient(headers=h, follow_redirects=True, timeout=10.0) as client:
                    res = await client.get(first_src)
                    print(f"Status: {res.status_code}, Content-Type: {res.headers.get('content-type')}")
                    print(f"Body (first 200 chars): {res.text[:200]}")
            except Exception as e:
                print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_moon())
