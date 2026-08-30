import asyncio
import os
import sys
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import moviesdrive_resolver as resolver
import moviesdrive_perf as perf

async def test_all_reacher_links():
    post_url = "https://new3.moviesdrive.christmas/reacher-season-1-4/"
    
    for season in [1, 2]:
        candidates = await resolver.collect_candidates(post_url, media_type="series", season_num=season, episode_num=1)
        print(f"\n================ Season {season} ================", flush=True)
        for c in candidates:
            arc = c.get("archive_url")
            print(f"\nResolving candidate: {c.get('label')} ({c.get('quality')}) -> {arc}", flush=True)
            resolved = await resolver.resolve_candidate(c)
            print(f"  Resolved: {resolved}", flush=True)
            if resolved and resolved.get("url"):
                u = resolved["url"]
                try:
                    async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                        r = await client.head(u, headers={"User-Agent": perf.USER_AGENT, "Referer": "https://gamerxyt.com/"})
                        print(f"  Direct Link Test: HTTP {r.status_code} | Content-Type: {r.headers.get('content-type')} | Size: {r.headers.get('content-length')}", flush=True)
                except Exception as e:
                    print(f"  Direct Link Error: {e}", flush=True)

    await perf.aclose_client()

if __name__ == "__main__":
    asyncio.run(test_all_reacher_links())
