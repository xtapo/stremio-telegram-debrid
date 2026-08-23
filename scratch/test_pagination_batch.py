import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import uhdmovies_catalog as catalog

WP_ITEMS_PER_PAGE = 12
STREMIO_PAGE_SIZE = 24

async def get_test_batch(skip=0):
    target_start = max(0, skip)
    target_end = target_start + STREMIO_PAGE_SIZE
    start_wp_page = (target_start // WP_ITEMS_PER_PAGE) + 1
    end_wp_page = ((target_end - 1) // WP_ITEMS_PER_PAGE) + 1
    wp_pages = list(range(start_wp_page, end_wp_page + 1))

    print(f"skip={skip} -> WP pages {wp_pages}")
    results = await asyncio.gather(
        *[catalog.get_category_page("movies", page=p) for p in wp_pages]
    )

    all_items = []
    seen = set()
    for batch in results:
        for it in batch or []:
            it_id = it.get("id")
            if it_id and it_id not in seen:
                seen.add(it_id)
                all_items.append(it)

    offset_in_first_page = max(0, target_start - (start_wp_page - 1) * WP_ITEMS_PER_PAGE)
    selected = all_items[offset_in_first_page : offset_in_first_page + STREMIO_PAGE_SIZE]
    print(f"Returning {len(selected)} items. First: {selected[0]['name'] if selected else None}, Last: {selected[-1]['name'] if selected else None}")
    return selected

async def main():
    print("=== Testing Stremio Pagination ===")
    p1 = await get_test_batch(skip=0)
    p2 = await get_test_batch(skip=24)
    p3 = await get_test_batch(skip=48)
    
    # Check for overlaps
    ids_p1 = set(x['id'] for x in p1)
    ids_p2 = set(x['id'] for x in p2)
    ids_p3 = set(x['id'] for x in p3)
    print(f"Overlaps P1-P2: {len(ids_p1.intersection(ids_p2))}")
    print(f"Overlaps P2-P3: {len(ids_p2.intersection(ids_p3))}")
    print(f"Total unique movies across 3 pages: {len(ids_p1 | ids_p2 | ids_p3)}")

asyncio.run(main())
