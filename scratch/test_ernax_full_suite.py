import asyncio
import json
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
import httpx
from addon import app

async def test_ernax_endpoints():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        print("=== 1. Testing /ernax/manifest.json ===")
        res = await client.get("/ernax/manifest.json")
        print(f"Status: {res.status_code}")
        manifest = res.json()
        print(f"Name: {manifest.get('name')}, Catalogs count: {len(manifest.get('catalogs', []))}")
        assert res.status_code == 200
        assert manifest.get("id") == "community.ernax.stremio.addon"

        print("\n=== 2. Testing /ernax/catalog/movie/ernax_popular_movie.json ===")
        res = await client.get("/ernax/catalog/movie/ernax_popular_movie.json")
        print(f"Status: {res.status_code}")
        cat_data = res.json()
        metas = cat_data.get("metas", [])
        print(f"Metas count: {len(metas)}")
        if metas:
            print(f"Sample meta: {metas[0].get('name')} ({metas[0].get('id')})")
        assert res.status_code == 200
        assert len(metas) > 0

        print("\n=== 3. Testing /ernax/meta/movie/ernax:movie:550.json (Fight Club) ===")
        res = await client.get("/ernax/meta/movie/ernax:movie:550.json")
        print(f"Status: {res.status_code}")
        meta_data = res.json()
        meta = meta_data.get("meta", {})
        print(f"Title: {meta.get('name')}, Year: {meta.get('releaseInfo')}, Rating: {meta.get('imdbRating')}")
        assert res.status_code == 200
        assert "Fight Club" in meta.get("name", "")

        print("\n=== 4. Testing /ernax/meta/series/ernax:series:1396.json (Breaking Bad) ===")
        res = await client.get("/ernax/meta/series/ernax:series:1396.json")
        print(f"Status: {res.status_code}")
        meta_data = res.json()
        meta = meta_data.get("meta", {})
        videos = meta.get("videos", [])
        print(f"Title: {meta.get('name')}, Episodes count: {len(videos)}")
        if videos:
            print(f"First episode: {videos[0].get('title')} ({videos[0].get('id')})")
        assert res.status_code == 200
        assert len(videos) > 0

        print("\n=== 5. Testing /ernax/stream/movie/ernax:movie:550.json ===")
        res = await client.get("/ernax/stream/movie/ernax:movie:550.json")
        print(f"Status: {res.status_code}")
        stream_data = res.json()
        streams = stream_data.get("streams", [])
        print(f"Streams count: {len(streams)}")
        for s in streams:
            print(f"- [{s.get('name')}] {s.get('title', '').splitlines()[0]}")
            if s.get('url'):
                print(f"  URL: {s.get('url')[:80]}...")
            if s.get('externalUrl'):
                print(f"  External: {s.get('externalUrl')}")
        assert res.status_code == 200
        assert len(streams) > 0

        print("\n=== 6. Testing /ernax/stream/series/ernax:series:1396:1:1.json (Breaking Bad S01E01) ===")
        res = await client.get("/ernax/stream/series/ernax:series:1396:1:1.json")
        print(f"Status: {res.status_code}")
        stream_data = res.json()
        streams = stream_data.get("streams", [])
        print(f"Streams count: {len(streams)}")
        for s in streams:
            print(f"- [{s.get('name')}] {s.get('title', '').splitlines()[0]}")
        assert res.status_code == 200
        assert len(streams) > 0

        print("\n=== 7. Testing /ernax/subtitles/series/ernax:series:1396:1:1.json ===")
        res = await client.get("/ernax/subtitles/series/ernax:series:1396:1:1.json")
        print(f"Status: {res.status_code}")
        sub_data = res.json()
        subs = sub_data.get("subtitles", [])
        print(f"Subtitles count: {len(subs)}")
        if subs:
            print(f"Sample sub: lang={subs[0].get('lang')}, url={subs[0].get('url')[:60]}...")
        assert res.status_code == 200

        print("\n=== 8. Testing /api/system/addons (Dashboard Addons API) ===")
        res = await client.get("/api/system/addons")
        print(f"Status: {res.status_code}")
        addons = res.json().get("addons", [])
        ernax_addon = next((a for a in addons if a.get("id") == "ernax"), None)
        print(f"Ernax Addon found in dashboard: {ernax_addon is not None}")
        if ernax_addon:
            print(f"Ernax Name: {ernax_addon.get('name')}, Enabled: {ernax_addon.get('enabled')}")
        assert ernax_addon is not None

        print("\n=== 9. Testing /api/search?q=Fight+Club (Universal Dashboard Search) ===")
        res = await client.get("/api/search?q=Fight+Club")
        print(f"Status: {res.status_code}")
        search_data = res.json()
        results = search_data.get("results", [])
        ernax_results = [r for r in results if r.get("source_id") == "ernax" or r.get("source") == "Ernax Player"]
        print(f"Total search results: {len(results)}, Ernax results: {len(ernax_results)}")
        if ernax_results:
            print(f"Sample Ernax search item: {ernax_results[0].get('title')}")
        assert res.status_code == 200
        assert len(ernax_results) > 0

        print("\n=== 10. Testing /api/media/details?source=ernax&id=550&type=movie ===")
        res = await client.get("/api/media/details?source=ernax&id=550&type=movie")
        print(f"Status: {res.status_code}")
        details = res.json()
        print(f"Details Title: {details.get('title')}, Source: {details.get('source')}, Quality: {details.get('quality')}")
        assert res.status_code == 200
        assert "Fight Club" in details.get("title", "")

        print("\n🎉 ALL 10 TESTS PASSED SUCCESSFULLY! 🎉")

if __name__ == "__main__":
    asyncio.run(test_ernax_endpoints())
