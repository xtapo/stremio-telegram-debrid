import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
from fastapi import FastAPI
from vidking_router import vidking_router

app = FastAPI()
app.include_router(vidking_router, prefix="/vidking")

async def run():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Test movie catalog
        print("=== 1. Testing Movie Catalog (IMDb IDs) ===")
        r_cat = await client.get("/vidking/catalog/movie/vidking_popular_movie.json")
        metas = r_cat.json().get("metas", [])
        print(f"Catalog items count: {len(metas)}")
        for m in metas[:3]:
            print(f"  Movie: {m['name']} -> Stremio ID: {m['id']}")
            assert m["id"].startswith("tt"), f"Catalog ID is not IMDb ID: {m['id']}"

        # 2. Test series catalog
        print("\n=== 2. Testing Series Catalog (IMDb IDs) ===")
        r_cat_tv = await client.get("/vidking/catalog/series/vidking_trending_series.json")
        metas_tv = r_cat_tv.json().get("metas", [])
        print(f"Series items count: {len(metas_tv)}")
        for m in metas_tv[:3]:
            print(f"  Series: {m['name']} -> Stremio ID: {m['id']}")
            assert m["id"].startswith("tt"), f"TV Catalog ID is not IMDb ID: {m['id']}"

        # 3. Test series episode IDs
        tv_id = metas_tv[0]["id"]
        print(f"\n=== 3. Testing Episode IDs for {metas_tv[0]['name']} ({tv_id}) ===")
        r_meta_tv = await client.get(f"/vidking/meta/series/{tv_id}.json")
        episodes = r_meta_tv.json().get("meta", {}).get("videos", [])
        print(f"Episodes count: {len(episodes)}")
        for ep in episodes[:3]:
            print(f"  Episode: {ep['title']} -> ID: {ep['id']}")
            assert ep["id"].startswith("tt") and ":" in ep["id"], f"Episode ID invalid: {ep['id']}"

        # 4. Test Stream Resolution for Episode 1
        ep1_id = episodes[0]["id"]
        print(f"\n=== 4. Testing Stream Resolution for {ep1_id} ===")
        r_stream = await client.get(f"/vidking/stream/series/{ep1_id}.json")
        streams = r_stream.json().get("streams", [])
        print(f"Streams found: {len(streams)}")
        assert len(streams) > 0, "No streams resolved!"
        for s in streams[:2]:
            print(f"  * {s.get('name')}: {s.get('url')[:65]}...")

        # 5. Test Subtitle Resolution for Episode 1
        print(f"\n=== 5. Testing Subtitles for {ep1_id} ===")
        r_subs = await client.get(f"/vidking/subtitles/series/{ep1_id}.json")
        subs = r_subs.json().get("subtitles", [])
        print(f"Subtitles count: {len(subs)}")
        assert len(subs) > 0, "No subtitles resolved!"
        for sub in subs[:4]:
            print(f"  * [{sub.get('lang')}] {sub.get('name') or sub.get('id')}: {sub.get('url')[:60]}...")

    print("\n ALL SUBTITLE & IMDB BRIDGE TESTS PASSED PERFECTLY! ")

if __name__ == '__main__':
    asyncio.run(run())
