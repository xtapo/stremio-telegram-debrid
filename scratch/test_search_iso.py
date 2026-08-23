import sys
sys.path.insert(0, ".")
import asyncio
import httpx
from bs4 import BeautifulSoup
import fourkhdhub_catalog as catalog
import fourkhdhub_perf as perf

async def test_search():
    res = await catalog.search_fourkhdhub("Avatar")
    print(f"search_fourkhdhub('Avatar') returned {len(res)} items")
    for r in res:
        print("  Item:", r)

asyncio.run(test_search())
