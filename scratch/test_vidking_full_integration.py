import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
from fastapi import FastAPI

from vidking_router import vidking_router
from dashboard_router import dashboard_router

app = FastAPI()
app.include_router(vidking_router, prefix="/vidking")
app.include_router(dashboard_router)

async def run_tests():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("=== 1. Testing Vidking Manifest ===")
        r = await client.get("/vidking/manifest.json")
        assert r.status_code == 200, f"Manifest failed: {r.status_code}"
        data = r.json()
        assert data["id"] == "com.stremio.vidking.addon"
        print(" Manifest OK:", data["name"], "Catalogs:", len(data["catalogs"]))

        print("\n=== 2. Testing Vidking Catalogs ===")
        r = await client.get("/vidking/catalog/movie/vidking_popular_movie.json")
        assert r.status_code == 200
        cat_movies = r.json()
        assert len(cat_movies["metas"]) > 0
        print(f" Popular Movies ({len(cat_movies['metas'])} items): First = {cat_movies['metas'][0]['name']}")

        r = await client.get("/vidking/catalog/series/vidking_trending_series.json")
        assert r.status_code == 200
        cat_series = r.json()
        assert len(cat_series["metas"]) > 0
        print(f" Trending Series ({len(cat_series['metas'])} items): First = {cat_series['metas'][0]['name']}")

        print("\n=== 3. Testing Vidking Meta ===")
        # Movie Meta: Fight Club
        r = await client.get("/vidking/meta/movie/vidking:movie:550.json")
        assert r.status_code == 200
        meta = r.json().get("meta", {})
        assert meta.get("name") == "Fight Club"
        print(f" Movie Meta OK: {meta.get('name')} ({meta.get('releaseInfo')})")

        # TV Meta: Breaking Bad
        r = await client.get("/vidking/meta/series/vidking:series:1396.json")
        assert r.status_code == 200
        meta_tv = r.json().get("meta", {})
        assert meta_tv.get("name") == "Breaking Bad"
        assert len(meta_tv.get("videos", [])) > 0
        print(f" TV Meta OK: {meta_tv.get('name')} with {len(meta_tv.get('videos', []))} episodes")

        print("\n=== 4. Testing Vidking Stream Resolution ===")
        # Movie Stream: Fight Club
        r = await client.get("/vidking/stream/movie/vidking:movie:550.json")
        assert r.status_code == 200
        streams = r.json().get("streams", [])
        assert len(streams) > 0, "No streams resolved!"
        print(f" Movie Streams ({len(streams)} streams found):")
        for s in streams[:3]:
            print(f"   * {s.get('name')}: {s.get('url')[:65]}...")

        # TV Stream: Breaking Bad S01E01
        r = await client.get("/vidking/stream/series/vidking:series:1396:1:1.json")
        assert r.status_code == 200
        tv_streams = r.json().get("streams", [])
        assert len(tv_streams) > 0, "No TV streams resolved!"
        print(f" TV Streams ({len(tv_streams)} streams found):")
        for s in tv_streams[:3]:
            print(f"   * {s.get('name')}: {s.get('url')[:65]}...")

        # IMDb ID stream: Fight Club (tt0137523)
        r = await client.get("/vidking/stream/movie/tt0137523.json")
        assert r.status_code == 200
        imdb_streams = r.json().get("streams", [])
        assert len(imdb_streams) > 0, "No IMDb ID streams resolved!"
        print(f" IMDb ID (tt0137523) Streams ({len(imdb_streams)} streams found)")

        print("\n=== 5. Testing Dashboard Addons List ===")
        r = await client.get("/api/system/addons")
        assert r.status_code == 200
        addons = r.json().get("addons", [])
        vidking_addon = next((a for a in addons if a["id"] == "vidking"), None)
        assert vidking_addon is not None, "Vidking addon not found in Dashboard list!"
        print(f" Dashboard Addon OK: {vidking_addon['name']} | Manifest: {vidking_addon['manifests']['local']}")

        print("\n ALL TESTS PASSED SUCCESSFULLY! ")

if __name__ == '__main__':
    asyncio.run(run_tests())
