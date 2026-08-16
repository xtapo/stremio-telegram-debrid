import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
from fastapi.testclient import TestClient
from addon import app
from subtitles_service import extract_embedded_subtitle, translate_srt_fast_batch
import urllib.parse

client = TestClient(app)

async def test_hotd_embedded():
    # 1. Resolve streams for House of the Dragon S1E1 (tt11198330:1:1)
    print("1. Resolving streams for tt11198330:1:1...")
    r = client.get("/stream/series/tt11198330:1:1.json")
    data = r.json()
    streams = data.get("streams", [])
    print(f"Found {len(streams)} streams.")
    
    direct_urls = []
    for s in streams:
        u = s.get("url", "")
        if "http" in u and "stream_proxy" not in u:
            direct_urls.append(u)
        elif "url=" in u:
            parsed = urllib.parse.parse_qs(urllib.parse.urlsplit(u).query)
            if "url" in parsed:
                direct_urls.append(parsed["url"][0])
                
    print(f"Direct URLs count: {len(direct_urls)}")
    if not direct_urls:
        print("No direct URLs found!")
        return

    first_video_url = direct_urls[0]
    print(f"Testing direct video URL: {first_video_url[:80]}...")
    
    # 2. Extract embedded subtitle
    print("Extracting embedded subtitle from video...")
    srt = await extract_embedded_subtitle(first_video_url)
    if srt:
        print(f"Successfully extracted {len(srt)} bytes of EMBEDDED subtitle!")
        print("First 15 lines:")
        print("\n".join(srt.splitlines()[:15]))
        
        print("\nTranslating first 30 blocks...")
        vi_vtt = await translate_srt_fast_batch(srt)
        print("First 20 lines of translated VTT:")
        print("\n".join(vi_vtt.splitlines()[:20]))
    else:
        print("Could not extract embedded subtitle! Checking ffprobe output...")

if __name__ == '__main__':
    asyncio.run(test_hotd_embedded())
