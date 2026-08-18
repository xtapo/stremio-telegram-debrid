import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
from fastapi import FastAPI
from vidking_router import vidking_router

app = FastAPI()
app.include_router(vidking_router, prefix="/vidking")

async def test_subs():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("=== 1. Testing Manifest Resources ===", flush=True)
        r = await client.get("/vidking/manifest.json")
        res_names = [res if isinstance(res, str) else res.get("name") for res in r.json()["resources"]]
        print("Manifest resources:", res_names, flush=True)
        assert "subtitles" in res_names, "subtitles resource missing from manifest!"

        print("\n=== 2. Testing Movie Subtitles (Fight Club: vidking:movie:550) ===", flush=True)
        r_sub_m = await client.get("/vidking/subtitles/movie/vidking:movie:550.json")
        assert r_sub_m.status_code == 200, f"Status: {r_sub_m.status_code}"
        subs_m = r_sub_m.json().get("subtitles", [])
        print(f"Fight Club Subtitles Count: {len(subs_m)}", flush=True)
        for s in subs_m[:4]:
            print(f"  * [{s.get('lang')}] {s.get('name') or s.get('id')}: {s.get('url')[:60]}...", flush=True)
        assert len(subs_m) > 0, "No subtitles returned for Fight Club!"

        print("\n=== 3. Testing TV Subtitles (Breaking Bad S01E01: vidking:series:1396:1:1) ===", flush=True)
        r_sub_tv = await client.get("/vidking/subtitles/series/vidking:series:1396:1:1.json")
        assert r_sub_tv.status_code == 200, f"Status: {r_sub_tv.status_code}"
        subs_tv = r_sub_tv.json().get("subtitles", [])
        print(f"Breaking Bad S01E01 Subtitles Count: {len(subs_tv)}", flush=True)
        for s in subs_tv[:4]:
            print(f"  * [{s.get('lang')}] {s.get('name') or s.get('id')}: {s.get('url')[:60]}...", flush=True)
        assert len(subs_tv) > 0, "No subtitles returned for Breaking Bad S01E01!"

        print("\n=== 4. Testing Stream behaviorHints filename ===", flush=True)
        r_stream = await client.get("/vidking/stream/movie/vidking:movie:550.json")
        streams = r_stream.json().get("streams", [])
        first_stream = streams[0]
        bh = first_stream.get("behaviorHints", {})
        print("Stream behaviorHints:", bh, flush=True)
        assert bh.get("filename") is not None, "filename behaviorHint is missing!"

        print("\n ALL SUBTITLE TESTS PASSED! ", flush=True)

if __name__ == '__main__':
    asyncio.run(test_subs())
