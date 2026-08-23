import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import uhdmovies_catalog as catalog

import uhdmovies_perf as perf
import uhdmovies_resolver as resolver

async def test_e2e():
    movies = await catalog.get_category_page('movies', page=1)
    series = await catalog.get_category_page('tv-series', page=1)
    test_items = movies[:2] + series[:2]
    
    for item in test_items:
        print("\n" + "="*50)
        print("TESTING ITEM:", item['name'], item['url'])
        cands = await resolver.collect_candidates(item['url'])
        print(f"Candidates found ({len(cands)}):")
        for i, c in enumerate(cands[:5]):
            print(f"  [{i}] btn={c.get('btn_text')} | badge={c.get('badge')} | title={c.get('title')[:60]} | url={c.get('raw_url')[:60]}")

asyncio.run(test_e2e())
