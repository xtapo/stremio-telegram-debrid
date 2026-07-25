import sys
import os
sys.path.insert(0, os.path.abspath("."))

import asyncio
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from topxx_router import topxx_router

sys.stdout.reconfigure(encoding='utf-8')

app = FastAPI()
app.include_router(topxx_router, prefix="/topxx")

async def main():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        print("=== TEST GENRE 'Hentai 18+' MULTI-SKIP PAGINATION ===")
        all_ids_g = set()
        for skip in [0, 20, 40, 60, 100]:
            res = await client.get(f"/topxx/catalog/movie/topxx_the_loai/genre=Hentai%2018%2B/skip={skip}.json")
            metas = res.json().get("metas", [])
            ids = [m['id'] for m in metas]
            new_ids = set(ids) - all_ids_g
            all_ids_g.update(ids)
            print(f"Genre skip={skip:3d}: Returned {len(metas)} items, {len(new_ids)} new unique items. First: {metas[0]['name'] if metas else 'NONE'}")

        print("\n=== TEST COUNTRY 'Nhật Bản' MULTI-SKIP PAGINATION ===")
        all_ids_c = set()
        for skip in [0, 20, 40, 60, 100]:
            res = await client.get(f"/topxx/catalog/movie/topxx_quoc_gia/genre=Nh%E1%BA%ADt%20B%E1%BA%A3n/skip={skip}.json")
            metas = res.json().get("metas", [])
            ids = [m['id'] for m in metas]
            new_ids = set(ids) - all_ids_c
            all_ids_c.update(ids)
            print(f"Country skip={skip:3d}: Returned {len(metas)} items, {len(new_ids)} new unique items. First: {metas[0]['name'] if metas else 'NONE'}")

if __name__ == "__main__":
    asyncio.run(main())
