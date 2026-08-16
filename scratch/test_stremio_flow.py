import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import httpx
from addon import app

async def test_full_stremio_flow():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # 1. Fetch subtitles catalog
        resp = await client.get("/subtitles/series/tt11198330:1:3.json")
        print("1. /subtitles/series/tt11198330:1:3.json status:", resp.status_code)
        subs = resp.json().get("subtitles", [])
        print(f"Found {len(subs)} subtitle tracks:")
        for s in subs[:3]:
            print(f" - [{s.get('lang')}] {s.get('name')}: {s.get('url')}")
            
        if not subs:
            print("ERROR: No subtitles returned!")
            return
            
        ai_sub = subs[0]
        sub_url = ai_sub["url"].replace("http://testserver", "")
        print(f"\n2. Testing HEAD {sub_url} ...")
        head_resp = await client.head(sub_url)
        print("HEAD status:", head_resp.status_code)
        print("HEAD Content-Type:", head_resp.headers.get("content-type"))
        print("HEAD Access-Control-Allow-Origin:", head_resp.headers.get("access-control-allow-origin"))
        
        print(f"\n3. Testing GET {sub_url} ...")
        get_resp = await client.get(sub_url)
        print("GET status:", get_resp.status_code)
        print("GET Content-Type:", get_resp.headers.get("content-type"))
        print("GET Content Length:", len(get_resp.text), "characters")
        print("First 200 chars of VTT:")
        print(get_resp.text[:200])

if __name__ == '__main__':
    asyncio.run(test_full_stremio_flow())
