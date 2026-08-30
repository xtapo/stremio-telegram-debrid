import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import moviesdrive_resolver as resolver
import moviesdrive_perf as perf

async def test_reacher():
    post_url = "https://new3.moviesdrive.christmas/reacher-season-1-4/"
    html = await resolver.fetch_html(post_url)
    print("Fetched HTML length:", len(html) if html else 0)
    
    soup = resolver.post_content(html)
    buttons = await resolver._scrape_buttons(post_url)
    print(f"\nScraped {len(buttons)} buttons:")
    for b in buttons:
        print(f"Season: {b.get('season')} | Text: {b.get('text')} | URL: {b.get('url')}")

    print("\n--- Testing Candidates for S1 E1 ---")
    c1 = await resolver.collect_candidates(post_url, media_type="series", season_num=1, episode_num=1)
    for c in c1:
        print("S1E1 candidate:", c)

    print("\n--- Testing Candidates for S2 E1 ---")
    c2 = await resolver.collect_candidates(post_url, media_type="series", season_num=2, episode_num=1)
    for c in c2:
        print("S2E1 candidate:", c)

    print("\n--- Testing Candidates for S3 E1 ---")
    c3 = await resolver.collect_candidates(post_url, media_type="series", season_num=3, episode_num=1)
    for c in c3:
        print("S3E1 candidate:", c)

    await perf.aclose_client()

if __name__ == "__main__":
    asyncio.run(test_reacher())
