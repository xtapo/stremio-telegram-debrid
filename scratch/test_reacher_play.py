import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
from vidking_router import vidking_stream_handler

async def test_reacher_stream():
    # 1. Get streams for Reacher S01E01
    res = await vidking_stream_handler('series', 'tt9288030:1:1')
    streams = res.get('streams', [])
    print(f"Total streams for Reacher S01E01: {len(streams)}")
    
    client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)
    
    for i, s in enumerate(streams):
        url = s.get('url')
        name = s.get('name')
        title = s.get('title')
        print(f"\n--- Stream {i+1}: {name} ---")
        print(f"URL: {url}")
        
        # Test 1: Direct request without headers
        try:
            r1 = await client.get(url, headers={'User-Agent': 'Mozilla/5.0'})
            print(f"  [Direct] Status: {r1.status_code}, Content-Type: {r1.headers.get('content-type')}")
            if r1.status_code == 200:
                print(f"  [Direct] Body preview:\n{r1.text[:250]}")
            else:
                print(f"  [Direct] Body: {r1.text[:200]}")
        except Exception as e:
            print(f"  [Direct] Error: {e}")

        # Test 2: Request with Referer https://www.vidking.net/
        try:
            r2 = await client.get(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.vidking.net/', 'Origin': 'https://www.vidking.net'})
            print(f"  [With Referer] Status: {r2.status_code}")
        except Exception as e:
            print(f"  [With Referer] Error: {e}")

    await client.aclose()

if __name__ == '__main__':
    asyncio.run(test_reacher_stream())
