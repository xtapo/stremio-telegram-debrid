import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx
from config import Config

async def test_api():
    port = Config.PORT
    base = f"http://127.0.0.1:{port}/uhdmovies"
    client = httpx.AsyncClient(timeout=20.0)

    # 1. Manifest
    r_m = await client.get(f"{base}/manifest.json")
    print("Manifest Catalogs:", len(r_m.json().get("catalogs", [])))

    # 2. Page 1 (skip=0)
    r_p1 = await client.get(f"{base}/catalog/movie/uhdmovies_movies_latest.json")
    metas1 = r_p1.json().get("metas", [])
    print(f"Page 1 (skip=0): {len(metas1)} items -> First: {metas1[0]['name']}, Last: {metas1[-1]['name']}")

    # 3. Page 2 (skip=24)
    r_p2 = await client.get(f"{base}/catalog/movie/uhdmovies_movies_latest/skip=24.json")
    metas2 = r_p2.json().get("metas", [])
    print(f"Page 2 (skip=24): {len(metas2)} items -> First: {metas2[0]['name']}, Last: {metas2[-1]['name']}")

    # 4. Genre Filter (4K HDR)
    r_g = await client.get(f"{base}/catalog/movie/uhdmovies_movies_latest/genre=4K%20HDR.json")
    metas_g = r_g.json().get("metas", [])
    print(f"Genre 4K HDR: {len(metas_g)} items -> First: {metas_g[0]['name']}")

    # 5. Series Catalog
    r_s = await client.get(f"{base}/catalog/series/uhdmovies_series_latest.json")
    metas_s = r_s.json().get("metas", [])
    print(f"Series Catalog: {len(metas_s)} items -> First: {metas_s[0]['name']}")

asyncio.run(test_api())
