import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import asyncio
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from addon import app

client = TestClient(app)

def test_manifest():
    print("\n[TEST] UHDMovies Manifest...")
    res = client.get("/uhdmovies/manifest.json")
    assert res.status_code == 200, f"Manifest status: {res.status_code}"
    data = res.json()
    assert data["id"] == "com.stremio.uhdmovies.addon"
    print(f"✅ Manifest OK: {data['name']} (catalogs: {len(data.get('catalogs', []))})")

def test_catalogs():
    print("\n[TEST] UHDMovies Catalogs...")
    # Latest movies
    res = client.get("/uhdmovies/catalog/movie/uhdmovies_movies_latest.json")
    assert res.status_code == 200, f"Catalog status: {res.status_code}"
    data = res.json()
    metas = data.get("metas", [])
    assert len(metas) > 0, "No metas returned in latest movies"
    print(f"✅ Latest Movies Catalog returned {len(metas)} items (Sample: {metas[0]['name']})")
    
    # 4K HDR
    res_hdr = client.get("/uhdmovies/catalog/movie/uhdmovies_movies_4k_hdr.json")
    assert res_hdr.status_code == 200
    data_hdr = res_hdr.json()
    metas_hdr = data_hdr.get("metas", [])
    print(f"✅ 4K HDR Catalog returned {len(metas_hdr)} items")

def test_search():
    print("\n[TEST] UHDMovies Search...")
    res = client.get("/uhdmovies/catalog/movie/uhdmovies_movies_latest.json?search=avatar")
    assert res.status_code == 200
    data = res.json()
    metas = data.get("metas", [])
    assert len(metas) > 0, "No items returned for search 'avatar'"
    print(f"✅ Search 'avatar' returned {len(metas)} items (First: {metas[0]['name']})")
    return metas[0]

def test_meta(item):
    print("\n[TEST] UHDMovies Meta...")
    url = f"/uhdmovies/meta/{item['type']}/{item['id']}.json"
    print("Requesting Meta URL:", url)
    res = client.get(url)
    assert res.status_code == 200
    data = res.json()
    print("Meta response data:", data)
    meta = data.get("meta", {})
    assert meta.get("name"), f"No name in meta: {data}"
    print(f"✅ Meta OK: {meta.get('name')} | Year: {meta.get('year')} | Genres: {meta.get('genres')}")

def test_streams(item):
    print("\n[TEST] UHDMovies Streams by slug...")
    res = client.get(f"/uhdmovies/stream/{item['type']}/{item['id']}.json")
    assert res.status_code == 200
    data = res.json()
    streams = data.get("streams", [])
    assert len(streams) > 0, f"No streams returned for {item['id']}"
    print(f"✅ Streams OK: Returned {len(streams)} streams for {item['name']}")
    for s in streams[:3]:
        print(f"   - [{s.get('name')}] {s.get('title')[:60]}... -> URL: {s.get('url')[:60]}...")
    return streams[0]

def test_imdb_streams():
    print("\n[TEST] UHDMovies IMDb Bridge (Interstellar tt0816692)...")
    res = client.get("/uhdmovies/stream/movie/tt0816692.json")
    assert res.status_code == 200
    data = res.json()
    streams = data.get("streams", [])
    print(f"✅ IMDb Bridge OK: Returned {len(streams)} streams for Interstellar (tt0816692)")
    assert len(streams) > 0, "No streams found for Interstellar via IMDb bridge"
    for s in streams[:3]:
        print(f"   - [{s.get('name')}] {s.get('title')[:60]}...")

def test_subtitles(item):
    print("\n[TEST] UHDMovies Subtitles...")
    res = client.get(f"/uhdmovies/subtitles/{item['type']}/{item['id']}.json")
    assert res.status_code == 200
    data = res.json()
    subs = data.get("subtitles", [])
    print(f"✅ Subtitles OK: Returned {len(subs)} subtitle tracks")

def test_dashboard_addons():
    print("\n[TEST] Dashboard Addons Listing...")
    res = client.get("/api/system/addons")
    assert res.status_code == 200
    data = res.json()
    addons = data.get("addons", [])
    uhd_addon = next((a for a in addons if a["id"] == "uhdmovies"), None)
    assert uhd_addon is not None, "uhdmovies addon not in dashboard addons"
    print(f"✅ Dashboard Addons OK: Found UHDMovies Cinema ({uhd_addon['name']}) with public manifest {uhd_addon['manifests']['public']}")

if __name__ == '__main__':
    print("🚀 STARTING INTEGRATION TESTS FOR UHDMOVIES...")
    test_manifest()
    test_catalogs()
    first_item = test_search()
    test_meta(first_item)
    test_streams(first_item)
    test_imdb_streams()
    test_subtitles(first_item)
    test_dashboard_addons()
    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY!")
