import urllib.request
import urllib.parse
import json
import httpx
import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
from addon import app

async def test_playback_flow():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:7860") as client:
        print("1. Fetching stream list for Fight Club (550)...")
        res = await client.get("/ernax/stream/movie/ernax:movie:550.json")
        print(f"Status: {res.status_code}")
        data = res.json()
        streams = data.get("streams", [])
        print(f"Got {len(streams)} streams.")
        
        for idx, s in enumerate(streams):
            print(f"\n--- Stream #{idx+1}: {s.get('name')} | {s.get('title', '').splitlines()[0]} ---")
            stream_url = s.get("url")
            ext_url = s.get("externalUrl")
            print(f"URL: {stream_url}")
            print(f"External: {ext_url}")
            
            if stream_url:
                # If stream_url is localhost proxy
                if "stream_proxy" in stream_url:
                    parsed = urllib.parse.urlparse(stream_url)
                    path_and_query = parsed.path + "?" + parsed.query
                    print(f"Fetching proxy path: {path_and_query[:80]}...")
                    p_res = await client.get(path_and_query)
                    print(f"Proxy response status: {p_res.status_code}, Content-Type: {p_res.headers.get('content-type')}")
                    content = p_res.text
                    print(f"Content length: {len(content)}")
                    print("First 300 chars:")
                    print(content[:300])
                    
                    # If it has sub-playlists or segments, let's fetch the first one!
                    lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
                    if lines:
                        first_line = lines[0]
                        print(f"\nTesting first item URL: {first_line[:100]}")
                        parsed_sub = urllib.parse.urlparse(first_line)
                        sub_path = parsed_sub.path + "?" + parsed_sub.query
                        sub_res = await client.get(sub_path)
                        print(f"Sub-item response status: {sub_res.status_code}, Content-Type: {sub_res.headers.get('content-type')}, Length: {len(sub_res.content)}")
                        if sub_res.headers.get('content-type') and 'mpegurl' in sub_res.headers.get('content-type'):
                            print("Sub m3u8 content:")
                            print(sub_res.text[:300])
                            sub_lines = [l.strip() for l in sub_res.text.splitlines() if l.strip() and not l.startswith("#")]
                            if sub_lines:
                                seg_line = sub_lines[0]
                                print(f"\nTesting first video segment: {seg_line[:100]}")
                                seg_parsed = urllib.parse.urlparse(seg_line)
                                seg_path = seg_parsed.path + "?" + seg_parsed.query
                                seg_res = await client.get(seg_path)
                                print(f"Segment response status: {seg_res.status_code}, Content-Type: {seg_res.headers.get('content-type')}, bytes: {len(seg_res.content)}")
                else:
                    # Direct CDN url
                    print(f"Testing direct CDN fetch...")
                    try:
                        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as cdn_client:
                            cdn_res = await cdn_client.get(stream_url)
                            print(f"Direct CDN status: {cdn_res.status_code}, Content-Type: {cdn_res.headers.get('content-type')}")
                    except Exception as e:
                        print(f"Direct CDN failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_playback_flow())
