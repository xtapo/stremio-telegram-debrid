import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import uhdmovies_resolver as resolver
import uhdmovies_perf as perf

async def main():
    url = "https://uhdmovies.autos/download-supergirl-2026-dual-audio-hindi-english-2160p-4k-dv-hdr-4k-sdr-1080p-x264-web-dl-esubs/"
    print("Collecting candidates for Supergirl...", flush=True)
    cands = await resolver.collect_candidates(url)
    print(f"Candidates found: {len(cands)}", flush=True)
    for i, c in enumerate(cands):
        print(f"[{i}] {c['badge']} | {c['size']} | {c['title'][:60]}", flush=True)
    
    # Test resolving candidate 0
    top = cands[0]
    print(f"\nResolving top candidate ({top['badge']})...", flush=True)
    direct_url = await resolver.resolve_candidate(top)
    print(f"Resolved URL: {direct_url[:90] if direct_url else None}", flush=True)
    
    if direct_url:
        client = await perf.get_client()
        r = await client.get(direct_url, headers={"Range": "bytes=0-1024"})
        print(f"Stream verification: Status={r.status_code}, Length={len(r.content)}, Type={r.headers.get('content-type')}", flush=True)

asyncio.run(main())
