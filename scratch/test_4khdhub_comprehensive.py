import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")

import httpx
from fastapi.testclient import TestClient

from addon import app
from config import Config
import fourkhdhub_perf as perf
import fourkhdhub_resolver as resolver
import fourkhdhub_catalog as catalog
import fourkhdhub_router as router

async def run_tests():
    print("=" * 60)
    print("  RUNNING 4KHDHUB COMPREHENSIVE TEST SUITE")
    print("=" * 60)

    perf.CACHE.clear()
    if os.path.exists(perf.CACHE_FILE):
        try:
            os.remove(perf.CACHE_FILE)
        except Exception:
            pass
    client = TestClient(app)

    # Test 1: Manifest Endpoint
    print("\n[Test 1] Testing /4khdhub/manifest.json...")
    res = client.get("/4khdhub/manifest.json")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    manifest = res.json()
    assert manifest["id"] == "com.stremio.4khdhub.addon"
    assert len(manifest["catalogs"]) >= 4
    print(" -> Manifest OK:", manifest["name"], "| Catalogs:", len(manifest["catalogs"]))

    # Test 2: Catalog Endpoint (Latest Movies)
    print("\n[Test 2] Testing /4khdhub/catalog/movie/4khdhub_movies_latest.json...")
    res = client.get("/4khdhub/catalog/movie/4khdhub_movies_latest.json")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    cat_data = res.json()
    metas = cat_data.get("metas", [])
    assert len(metas) > 0, "Expected at least 1 movie item in catalog"
    sample = metas[0]
    print(f" -> Catalog OK: {len(metas)} items | First item: {sample.get('name')} (ID: {sample.get('id')})")

    # Test 3: Catalog Search Endpoint
    print("\n[Test 3] Testing /4khdhub/catalog/movie/4khdhub_movies_latest/search=Avatar.json...")
    res = client.get("/4khdhub/catalog/movie/4khdhub_movies_latest/search=Avatar.json")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    search_json = res.json()
    search_metas = search_json.get("metas", [])
    print(" -> search_metas length:", len(search_metas), "payload:", search_json)
    assert len(search_metas) > 0, f"Expected search results for 'Avatar', got {search_json}"
    print(f" -> Search OK: {len(search_metas)} results found for 'Avatar':")
    for sm in search_metas[:3]:
        print(f"    * {sm.get('name')} -> {sm.get('id')} (Poster: {sm.get('poster')[:40]}...)")

    # Test 4: Meta Endpoint
    sample_slug = sample.get("id").replace("4khdhub:", "")
    print(f"\n[Test 4] Testing /4khdhub/meta/movie/4khdhub:{sample_slug}.json...")
    res = client.get(f"/4khdhub/meta/movie/4khdhub:{sample_slug}.json")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    meta_obj = res.json().get("meta", {})
    assert meta_obj.get("name"), "Expected valid meta name"
    print(f" -> Meta OK: {meta_obj.get('name')} | Year: {meta_obj.get('year')} | Genres: {meta_obj.get('genres')}")

    # Test 5: Stream Endpoint with Native 4KHDHub ID
    print(f"\n[Test 5] Testing /4khdhub/stream/movie/4khdhub:{sample_slug}.json...")
    res = client.get(f"/4khdhub/stream/movie/4khdhub:{sample_slug}.json")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    streams = res.json().get("streams", [])
    assert len(streams) > 0, "Expected at least 1 stream item"
    print(f" -> Streams OK: Found {len(streams)} streams for {sample_slug}:")
    for s in streams[:4]:
        name_s = s.get('name', '').encode('ascii', 'replace').decode('ascii')
        title_s = s.get('title', '').encode('ascii', 'replace').decode('ascii')
        print(f"    * {name_s}\n      {title_s}\n      URL: {s.get('url')[:80]}...")

    # Test 6: Stream Endpoint with IMDb ID (tt0499549 - Avatar)
    print("\n[Test 6] Testing IMDb ID Stream mapping (tt0499549 - Avatar)...")
    res = client.get("/4khdhub/stream/movie/tt0499549.json")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    imdb_streams = res.json().get("streams", [])
    assert len(imdb_streams) > 0, "Expected streams for Avatar by IMDb ID"
    print(f" -> IMDb Mapping OK: Found {len(imdb_streams)} streams for Avatar (tt0499549):")
    for s in imdb_streams[:4]:
        name_s = s.get('name', '').encode('ascii', 'replace').decode('ascii')
        title_s = s.get('title', '').encode('ascii', 'replace').decode('ascii')
        print(f"    * {name_s}\n      {title_s}")

    # Test 7: Stream Endpoint with Series IMDb ID (tt10234724:5:1 - Outer Banks S05E01)
    print("\n[Test 7] Testing Series IMDb ID Stream mapping (tt10234724:5:1 - Outer Banks S05E01)...")
    res = client.get("/4khdhub/stream/series/tt10234724:5:1.json")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    series_streams = res.json().get("streams", [])
    print(f" -> Series IMDb Mapping OK: Found {len(series_streams)} streams for Outer Banks S05E01:")
    for s in series_streams[:4]:
        name_s = s.get('name', '').encode('ascii', 'replace').decode('ascii')
        title_s = s.get('title', '').encode('ascii', 'replace').decode('ascii')
        print(f"    * {name_s}\n      {title_s}")

    # Test 8: Playback Resolution (302 Redirect to CDN)
    if imdb_streams:
        playback_url = imdb_streams[0].get("url")
        # Strip domain if local
        path = "/" + "/".join(playback_url.split("/")[3:])
        print(f"\n[Test 8] Testing Playback redirect: {path[:80]}...")
        res = client.get(path, follow_redirects=False)
        assert res.status_code == 302, f"Expected 302 redirect, got {res.status_code}"
        location = res.headers.get("location")
        print(" -> Playback Redirect OK: 302 ->", location[:100], "...")
        assert "http" in location

    # Test 9: Dashboard Addons API
    print("\n[Test 9] Testing /api/system/addons...")
    res = client.get("/api/system/addons")
    assert res.status_code == 200
    addons = res.json().get("addons", [])
    fourkhd_addon = next((a for a in addons if a.get("id") == "4khdhub"), None)
    assert fourkhd_addon is not None, "Expected '4khdhub' in dashboard addons"
    print(" -> Dashboard Addons API OK: Found 4KHDHub in system addons list!")

    print("\n" + "=" * 60)
    print("  ALL 4KHDHUB TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 60)

asyncio.run(run_tests())
