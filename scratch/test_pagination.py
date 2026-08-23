import sys
sys.path.insert(0, ".")
import asyncio
import fourkhdhub_catalog as catalog
import fourkhdhub_perf as perf

async def test_pagination():
    perf.CACHE.clear()
    print("Testing get_catalog_items with batching...")

    # Batch 1: skip=0
    items_0 = await catalog.get_catalog_items("Phim Mới", skip=0)
    print(f"skip=0 returned {len(items_0)} items:")
    for it in items_0[:4]:
        print(f"  * {it['name']} ({it['id']})")
    print(f"  ... last item: {items_0[-1]['name']} ({items_0[-1]['id']})")

    # Batch 2: skip=54
    items_54 = await catalog.get_catalog_items("Phim Mới", skip=54)
    print(f"\nskip=54 returned {len(items_54)} items:")
    for it in items_54[:4]:
        print(f"  * {it['name']} ({it['id']})")
    print(f"  ... last item: {items_54[-1]['name']} ({items_54[-1]['id']})")

    # Verify no duplication between page 1 and page 2
    ids_0 = {it.get('slug') or it.get('name') for it in items_0}
    ids_54 = {it.get('slug') or it.get('name') for it in items_54}
    overlap = ids_0.intersection(ids_54)
    print(f"\nOverlap between batch 1 and 2: {len(overlap)} items (Expected 0)")

asyncio.run(test_pagination())
