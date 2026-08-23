import asyncio
import os
import sys
import re
import urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import uhdmovies_perf as perf
import uhdmovies_resolver as resolver

async def test_supergirl():
    url = "https://uhdmovies.autos/download-supergirl-2026-dual-audio-hindi-english-2160p-4k-dv-hdr-4k-sdr-1080p-x264-web-dl-esubs/"
    print("Collecting candidates for Supergirl...")
    cands = await resolver.collect_candidates(url)
    print(f"Found {len(cands)} candidates:")
    for i, c in enumerate(cands):
        print(f"  [{i}] badge={c['badge']} | size={c['size']} | btn={c['btn_text']} | title={c['title'][:70]}")
        print(f"       raw_url={c['raw_url'][:70]}")
        
    for i, c in enumerate(cands):
        print(f"\nResolving candidate [{i}] ({c['badge']})...")
        res = await resolver.resolve_candidate(c)
        print(f"Result [{i}]: {res[:90] if res else None}")
        if res:
            client = await perf.get_client()
            r_vid = await client.get(res, headers={"Range": "bytes=0-1024", "User-Agent": perf.USER_AGENT})
            print(f"Stream verification: Status={r_vid.status_code}, Length={len(r_vid.content)}, Content-Type={r_vid.headers.get('content-type')}")
            
asyncio.run(test_supergirl())
