import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import uhdmovies_catalog as catalog
import uhdmovies_perf as perf
from test_distinct_desc import parse_post_candidates_v3

async def test_multi():
    movies = await catalog.get_category_page('movies', page=1)
    series = await catalog.get_category_page('tv-series', page=1)
    hdr_movies = await catalog.get_category_page('4k-hdr', page=1)
    
    test_set = [movies[0], hdr_movies[0], series[0]]
    for item in test_set:
        print("\n" + "="*60)
        print("TESTING:", item['name'], item['url'])
        html = await perf.fetch_text(item['url'])
        cands = parse_post_candidates_v3(html)
        print(f"Candidates found: {len(cands)}")
        for i, c in enumerate(cands[:5]):
            print(f"  [{i}] btn={c['btn_text']!r} | badge={c['badge']} | size={c['size']} | ep={c['episode']} | rank={c['rank']} | desc={c['title'][:70]}")

asyncio.run(test_multi())
