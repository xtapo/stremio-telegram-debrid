import sys
import os
sys.path.insert(0, ".")

import asyncio
from fastapi.testclient import TestClient
from addon import app
import fourkhdhub_perf as perf

async def test_subtitles():
    perf.CACHE.clear()
    client = TestClient(app)

    print("=== Testing 4KHDHub Subtitles Endpoints ===")

    # 1. Custom 4KHDHub ID subtitles
    print("\n[Test 1] GET /4khdhub/subtitles/movie/4khdhub:avatar-movie-774.json")
    res = client.get("/4khdhub/subtitles/movie/4khdhub:avatar-movie-774.json")
    print("Status:", res.status_code)
    data = res.json()
    subs = data.get("subtitles", [])
    print(f"Returned {len(subs)} subtitle tracks:")
    for s in subs[:5]:
        print(f"  * [{s.get('lang')}] {s.get('name') or s.get('id')} -> {s.get('url')[:60]}...")

    # 2. IMDb ID subtitles
    print("\n[Test 2] GET /4khdhub/subtitles/movie/tt0499549.json")
    res_imdb = client.get("/4khdhub/subtitles/movie/tt0499549.json")
    print("Status:", res_imdb.status_code)
    subs_imdb = res_imdb.json().get("subtitles", [])
    print(f"Returned {len(subs_imdb)} subtitle tracks:")
    for s in subs_imdb[:5]:
        print(f"  * [{s.get('lang')}] {s.get('name') or s.get('id')} -> {s.get('url')[:60]}...")

    # 3. Stream item embedded subtitles
    print("\n[Test 3] GET /4khdhub/stream/movie/4khdhub:avatar-movie-774.json")
    res_stream = client.get("/4khdhub/stream/movie/4khdhub:avatar-movie-774.json")
    streams = res_stream.json().get("streams", [])
    print("Stream count:", len(streams))
    if streams:
        print("First stream keys:", list(streams[0].keys()))
        print("First stream content:", streams[0])
        embedded_subs = streams[0].get("subtitles", [])
        print(f"Stream item has {len(embedded_subs)} embedded subtitle tracks!")
        for es in embedded_subs:
            print(f"  * [{es.get('lang')}] {es.get('name') or es.get('id')} -> {es.get('url')[:60]}...")

asyncio.run(test_subtitles())
