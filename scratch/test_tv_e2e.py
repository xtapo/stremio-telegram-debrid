import urllib.parse
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

async def test_tv_end_to_end():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:7860") as client:
        print("Fetching Breaking Bad S01E01 streams...")
        res = await client.get("/ernax/stream/series/ernax:series:1396:1:1.json")
        print(f"Status: {res.status_code}")
        streams = res.json().get("streams", [])
        print(f"Got {len(streams)} streams.")
        
        for s in streams:
            url = s.get("url")
            if url and "stream_proxy" in url:
                parsed = urllib.parse.urlparse(url)
                p_res = await client.get(parsed.path + "?" + parsed.query)
                print(f"[{s.get('name')}] Proxy Status: {p_res.status_code}, Length: {len(p_res.content)}")
                lines = [l.strip() for l in p_res.text.splitlines() if l.strip() and not l.startswith("#")]
                if lines:
                    sub_parsed = urllib.parse.urlparse(lines[0])
                    seg_res = await client.get(sub_parsed.path + "?" + sub_parsed.query)
                    print(f"  -> Segment status: {seg_res.status_code}, bytes: {len(seg_res.content)}, Content-Type: {seg_res.headers.get('content-type')}")

if __name__ == "__main__":
    asyncio.run(test_tv_end_to_end())
