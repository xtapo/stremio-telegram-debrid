import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import uhdmovies_resolver as resolver
import uhdmovies_perf as perf

test_cases = [
    ("Movie 1 (Google User Content)", "https://uhdmovies.autos/download-supergirl-2026-dual-audio-hindi-english-2160p-4k-dv-hdr-4k-sdr-1080p-x264-web-dl-esubs/"),
    ("Movie 2 (Workers CDN)", "https://uhdmovies.autos/download-somebody-2025-dual-audio-hindi-english-1080p-x264-hevc-web-dl-esubs/"),
    ("Movie 3 (4K REMUX)", "https://uhdmovies.autos/download-rush-2013-dual-audio-hindi-english-2160p-4k-1080p-10bit-hevc-blu-ray-esubs/"),
    ("Series 1 (Ep 1)", "https://uhdmovies.autos/download-taxi-driver-2021-dual-audio-hindi-english-1080p-x264-web-dl-esubs/"),
]

async def run_all():
    client = await perf.get_client()
    for name, url in test_cases:
        print(f"\n==========================================")
        print(f"Testing: {name}")
        cands = await resolver.collect_candidates(url, episode=1 if "Series" in name else None)
        if not cands:
            print("  [FAIL] No candidates found!")
            continue
        top = cands[0]
        print(f"  Top Candidate: {top['badge']} | {top['size']} | {top['btn_text']}")
        resolved = await resolver.resolve_candidate(top)
        if not resolved:
            print("  [FAIL] Could not resolve candidate!")
            continue
        print(f"  Resolved URL: {resolved[:80]}...")
        try:
            async with client.stream("GET", resolved, headers={"Range": "bytes=0-1024", "User-Agent": perf.USER_AGENT}) as resp:
                print(f"  Playback test: Status={resp.status_code}, Type={resp.headers.get('content-type')}")
                if resp.status_code in (200, 206):
                    print("  [SUCCESS] STREAM PLAYABLE!")
                else:
                    print("  [WARN] Unexpected status code")
        except Exception as e:
            print(f"  [FAIL] Stream error: {e}")

asyncio.run(run_all())
