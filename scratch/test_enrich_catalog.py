import sys
import os
sys.path.insert(0, ".")

import asyncio
import fourkhdhub_catalog as catalog
import fourkhdhub_perf as perf

async def test_enrich():
    print("Fetching page 1 movies...")
    cards = await catalog.get_catalog_page("movies", page=1)
    print(f"Parsed {len(cards)} cards from 4khdhub.")
    for c in cards[:5]:
        print(f"  Before: {c['name']} (Year: {c['year']}) -> ID: {c['id']}")

    print("\nEnriching with IMDb IDs...")
    enriched = await catalog.enrich_catalog_with_imdb(cards)
    for c in enriched[:5]:
        print(f"  After:  {c['name']} (Year: {c['year']}) -> ID: {c['id']}")

if __name__ == "__main__":
    asyncio.run(test_enrich())
