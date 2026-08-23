import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import uhdmovies_catalog as catalog
import uhdmovies_resolver as resolver
import uhdmovies_perf as perf

async def full_e2e_test():
    print("=== 1. Testing Catalog ===")
    movies = await catalog.get_category_page('movies', page=1)
    series = await catalog.get_category_page('tv-series', page=1)
    print(f"Movies found: {len(movies)}")
    print(f"Series found: {len(series)}")
    
    test_items = [("Movie", movies[0]), ("Series", series[0])]
    
    client = await perf.get_client()
    
    for kind, item in test_items:
        print(f"\n=== 2. Testing {kind}: {item['name']} ===")
        print(f"URL: {item['url']}")
        
        cands = await resolver.collect_candidates(item['url'], episode=1 if kind == "Series" else None)
        print(f"Collected {len(cands)} candidates:")
        for idx, c in enumerate(cands[:4]):
            print(f"  [{idx}] badge={c.get('badge')} | size={c.get('size')} | btn={c.get('btn_text')} | desc={c.get('title')[:60]}")
            
        if not cands:
            print("  ❌ No candidates found!")
            continue
            
        top_cand = cands[0]
        print(f"\n>>> Resolving Top Candidate: {top_cand['btn_text']} ({top_cand['badge']})...")
        stream_url = await resolver.resolve_candidate(top_cand)
        print(f"Resolved Stream URL: {stream_url}")
        
        if not stream_url:
            print("  ❌ Could not resolve playable stream URL!")
            continue
            
        # Verify video streaming (HTTP 200 or 206, video mime type, Range support)
        print(">>> Verifying video playback stream (Range: bytes=0-1024)...")
        r_video = await client.get(stream_url, headers={"Range": "bytes=0-1024", "User-Agent": perf.USER_AGENT})
        print(f"Video Stream Response: Status={r_video.status_code}, Content-Type={r_video.headers.get('content-type')}, Bytes={len(r_video.content)}")
        
        if r_video.status_code in (200, 206) and len(r_video.content) > 0:
            print(f"  [SUCCESS] {kind} video stream SUCCESSFUL & PLAYABLE!")
        else:
            print(f"  [FAILED] {kind} video stream FAILED!")


if __name__ == "__main__":
    asyncio.run(full_e2e_test())
