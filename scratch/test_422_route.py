import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath("."))

from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from topxx_router import topxx_router

sys.stdout.reconfigure(encoding='utf-8')

app = FastAPI()
app.include_router(topxx_router, prefix="/topxx")

async def main():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        urls_to_test = [
            "/topxx/catalog/movie/topxx_quoc_gia/genre=Vi%E1%BB%87t%20Nam.json",
            "/topxx/catalog/movie/topxx_quoc_gia/genre=Vi%E1%BB%87t%20Nam&skip=100.json",
            "/topxx/catalog/movie/topxx_quoc_gia/genre=Vi%E1%BB%87t%20Nam/skip=100.json",
            "/topxx/catalog/movie/topxx_quoc_gia/skip=100/genre=Vi%E1%BB%87t%20Nam.json",
            "/topxx/catalog/movie/topxx_quoc_gia/genre=Vi%E1%BB%87t%20Nam.json?skip=100",
            "/topxx/catalog/movie/topxx_the_loai/genre=Hentai%2018%2B&skip=20.json",
            "/topxx/catalog/movie/topxx_phim_moi/skip=30.json"
        ]
        for url in urls_to_test:
            res = await client.get(url)
            metas = res.json().get('metas', []) if res.status_code == 200 else []
            print(f"URL: {url}")
            print(f"  Status: {res.status_code} | Metas count: {len(metas)}")
            if metas:
                print(f"  First title: {metas[0]['name']}")
            print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main())
