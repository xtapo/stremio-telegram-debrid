import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import httpx
from fastapi import FastAPI
from movies2watch_router import movies2watch_router
from dashboard_router import dashboard_router

app = FastAPI()
app.include_router(movies2watch_router, prefix="/movies2watch")
app.include_router(dashboard_router)

async def run_tests():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("=== 1. Testing Manifest ===")
        r = await client.get("/movies2watch/manifest.json")
        print("Manifest status:", r.status_code)
        manifest = r.json()
        print("Manifest ID:", manifest.get("id"), "Name:", manifest.get("name"))
        assert manifest.get("id") == "com.stremio.movies2watch.addon"
        assert len(manifest.get("catalogs", [])) >= 3
        print("Catalogs count:", len(manifest.get("catalogs", [])))

        print("\n=== 2. Testing Latest Movies Catalog ===")
        r_cat_m = await client.get("/movies2watch/catalog/movie/movies2watch_phim_moi_movie.json")
        print("Latest Movies status:", r_cat_m.status_code)
        metas_m = r_cat_m.json().get("metas", [])
        print(f"Found {len(metas_m)} movies:")
        for m in metas_m[:3]:
            print(f" - [{m.get('id')}] {m.get('name')} ({m.get('releaseInfo')})")
        assert len(metas_m) > 0

        print("\n=== 3. Testing Latest Series Catalog ===")
        r_cat_s = await client.get("/movies2watch/catalog/series/movies2watch_phim_moi_series.json")
        print("Latest Series status:", r_cat_s.status_code)
        metas_s = r_cat_s.json().get("metas", [])
        print(f"Found {len(metas_s)} series:")
        for s in metas_s[:3]:
            print(f" - [{s.get('id')}] {s.get('name')} ({s.get('releaseInfo')})")
        assert len(metas_s) > 0

        print("\n=== 4. Testing Search ===")
        r_search = await client.get("/movies2watch/catalog/movie/movies2watch_phim_moi_movie/search=oppenheimer.json")
        print("Search status:", r_search.status_code)
        metas_search = r_search.json().get("metas", [])
        print(f"Found {len(metas_search)} search results:")
        for s in metas_search[:3]:
            print(f" - [{s.get('id')}] {s.get('name')}")
        assert len(metas_search) > 0

        print("\n=== 5. Testing Movie Meta ===")
        r_meta_m = await client.get("/movies2watch/meta/movie/movies2watch:movie:oppenheimer-51311.json")
        print("Movie Meta status:", r_meta_m.status_code)
        meta_m = r_meta_m.json().get("meta", {})
        print("Movie Name:", meta_m.get("name"))
        print("Poster:", meta_m.get("poster")[:60] if meta_m.get("poster") else None)
        print("Genres:", meta_m.get("genres"))
        assert meta_m.get("name") is not None

        print("\n=== 6. Testing Series Meta & Episodes ===")
        r_meta_s = await client.get("/movies2watch/meta/series/movies2watch:series:avatar-the-last-airbender-67006.json")
        print("Series Meta status:", r_meta_s.status_code)
        meta_s = r_meta_s.json().get("meta", {})
        print("Series Name:", meta_s.get("name"))
        videos = meta_s.get("videos", [])
        print(f"Extracted {len(videos)} episodes across seasons:")
        for v in videos[:4]:
            print(f" - [{v.get('id')}] {v.get('title')}")
        assert len(videos) > 0

        print("\n=== 7. Testing Movie Streams ===")
        r_stream_m = await client.get("/movies2watch/stream/movie/movies2watch:movie:oppenheimer-51311.json")
        print("Movie Streams status:", r_stream_m.status_code)
        streams_m = r_stream_m.json().get("streams", [])
        print(f"Found {len(streams_m)} streams for Oppenheimer")
        for str_item in streams_m[:4]:
            s_name = str(str_item.get('name', '')).encode('ascii', 'ignore').decode('ascii').replace('\n', ' ')
            s_url = str(str_item.get('url') or str_item.get('externalUrl') or '')[:70]
            print(f" * {s_name} -> {s_url}")
        assert len(streams_m) > 0

        print("\n=== 8. Testing Series Streams ===")
        r_stream_s = await client.get("/movies2watch/stream/series/movies2watch:series:avatar-the-last-airbender-67006:1:1.json")
        print("Series Streams status:", r_stream_s.status_code)
        streams_s = r_stream_s.json().get("streams", [])
        print(f"Found {len(streams_s)} streams for Avatar S1E1")
        for str_item in streams_s[:4]:
            s_name = str(str_item.get('name', '')).encode('ascii', 'ignore').decode('ascii').replace('\n', ' ')
            s_url = str(str_item.get('url') or str_item.get('externalUrl') or '')[:70]
            print(f" * {s_name} -> {s_url}")
        assert len(streams_s) > 0

        print("\n=== 9. Testing Dashboard Addons Integration ===")
        r_addons = await client.get("/api/system/addons")
        print("Dashboard Addons status:", r_addons.status_code)
        addons_list = r_addons.json().get("addons", [])
        m2w_addon = next((a for a in addons_list if a.get("id") == "movies2watch"), None)
        print("Movies2Watch Addon found in dashboard:", m2w_addon is not None)
        if m2w_addon:
            print(" - Name:", m2w_addon.get("name"))
            print(" - Manifest Public:", m2w_addon.get("manifests", {}).get("public"))
        assert m2w_addon is not None

        print("\n=== ALL TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    asyncio.run(run_tests())
