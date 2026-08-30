import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import moviesdrive_resolver as resolver
import moviesdrive_perf as perf

async def test_all_seasons():
    perf.CACHE.clear()
    post_url = "https://new3.moviesdrive.christmas/reacher-season-1-4/"
    
    print("=== Testing Reacher Multi-Season Accuracy ===")
    for s in range(1, 5):
        candidates = await resolver.collect_candidates(
            post_url, media_type="series", season_num=s, episode_num=1
        )
        print(f"\nSeason {s} Ep 1 found {len(candidates)} candidates:")
        for c in candidates:
            print(f"  - Quality: {c['quality']} | Rank: {c['rank']} | Archive: {c['archive_url']} | Label: {c['label'][:50]}")
            
        # Verify archive URLs match expected for each season:
        if s == 1:
            assert all(arc in ["https://mdrive.lol/archive/6762/", "https://mdrive.lol/archive/6759/", "https://mdrive.lol/archive/6756/"] for arc in [c['archive_url'] for c in candidates]), f"Season 1 got wrong archives!"
        elif s == 2:
            assert len(candidates) >= 3, f"Season 2 expected >= 3 candidates, got {len(candidates)}"
            assert all(arc in ["https://mdrive.lol/archive/6775/", "https://mdrive.lol/archive/6773/", "https://mdrive.lol/archive/6771/"] for arc in [c['archive_url'] for c in candidates]), f"Season 2 got wrong archives!"
        elif s == 3:
            assert all(arc in ["https://mdrive.lol/archive/6793/", "https://mdrive.lol/archive/6789/", "https://mdrive.lol/archive/6787/", "https://mdrive.lol/archive/6785/", "https://mdrive.lol/archive/6783/"] for arc in [c['archive_url'] for c in candidates]), f"Season 3 got wrong archives!"
        elif s == 4:
            assert all(arc in ["https://mdrive.lol/archive/15695/", "https://mdrive.lol/archive/15686/", "https://mdrive.lol/archive/15691/", "https://mdrive.lol/archive/15688/", "https://mdrive.lol/archive/15693/"] for arc in [c['archive_url'] for c in candidates]), f"Season 4 got wrong archives!"

    print("\n[SUCCESS] ALL SEASON ACCURACY CHECKS PASSED PERFECTLY!")
    await perf.aclose_client()

if __name__ == "__main__":
    asyncio.run(test_all_seasons())
