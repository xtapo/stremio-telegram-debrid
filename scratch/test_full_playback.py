import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
from fastapi import FastAPI
from vidking_router import vidking_router

app = FastAPI()
app.include_router(vidking_router, prefix="/vidking")

async def test_full_playback():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Fetch streams for Reacher S01E01
        print("=== 1. Requesting Streams for Reacher S01E01 ===")
        r_stream = await client.get("/vidking/stream/series/tt9288030:1:1.json")
        assert r_stream.status_code == 200
        streams = r_stream.json().get("streams", [])
        print(f"Total streams returned: {len(streams)}")
        assert len(streams) > 0
        
        # 2. Test fetching the first stream (4K or 1080p) via stream proxy
        first_stream = streams[0]
        stream_url = first_stream.get("url")
        print(f"\nTesting top stream: {first_stream.get('name')}")
        print(f"Proxied URL: {stream_url}")
        
        # Replace 'http://127.0.0.1:7860' with 'http://test' for ASGI client
        test_url = stream_url.replace("http://127.0.0.1:7860", "").replace("http://localhost:7860", "")
        
        print("\n=== 2. Fetching M3U8 Playlist through Proxy ===")
        r_m3u8 = await client.get(test_url)
        print(f"M3U8 Status: {r_m3u8.status_code}")
        print(f"Content-Type: {r_m3u8.headers.get('content-type')}")
        assert r_m3u8.status_code == 200, f"Proxy failed with status {r_m3u8.status_code}"
        assert "#EXTM3U" in r_m3u8.text, "Playlist does not contain #EXTM3U header!"
        
        # 3. Extract first proxied segment URL and test fetching it
        lines = r_m3u8.text.splitlines()
        proxied_chunk_url = None
        for line in lines:
            if "/vidking/stream_proxy?url=" in line:
                if 'URI="' in line:
                    proxied_chunk_url = line.split('URI="')[1].split('"')[0]
                else:
                    proxied_chunk_url = line.strip()
                break
                
        print(f"\n=== 3. Testing Video Chunk fetching via Proxy ===")
        print(f"Chunk URL: {proxied_chunk_url[:100]}...")
        assert proxied_chunk_url is not None, "No proxied segment URL found in rewritten playlist!"
        
        test_chunk_url = proxied_chunk_url.replace("http://127.0.0.1:7860", "").replace("http://localhost:7860", "").replace("http://test", "")
        r_chunk = await client.get(test_chunk_url)
        print(f"Video Chunk Status: {r_chunk.status_code}")
        print(f"Chunk Content-Length: {len(r_chunk.content)} bytes")
        assert r_chunk.status_code == 200, f"Chunk request failed with status {r_chunk.status_code}"
        assert len(r_chunk.content) > 1000, "Chunk content is unexpectedly small!"
        
        print("\n🎉 PLAYBACK PROXY VERIFIED 100% WORKING! ZERO 403 ERRORS!")

if __name__ == '__main__':
    asyncio.run(test_full_playback())
