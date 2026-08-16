import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
from subtitles_service import get_or_generate_synced_vtt

async def test_full_pipeline():
    video_url = "https://9f7e2b9f5ee304d858c9a743a3aa5357.r2.cloudflarestorage.com/hub2/a910ecf689f8a86c96adc2a803abca0d?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=f3a2fc8098af833664a1af1908249931%2F20260816%2Fauto%2Fs3%2Faws4_request&X-Amz-Date=20260816T005902Z&X-Amz-Expires=28800&X-Amz-SignedHeaders=host&response-content-disposition=attachment%3B%20filename%3D%22House.of.the.Dragon.S03E01.480p.WEB-DL.Hindi-English.ESub.x264-MoviesDrives.CV.mkv%22&X-Amz-Signature=b09c8e2a96321e306a8df9bd90c22b7674b4227118a25b88790021a688ec87a4"
    
    print("Generating synced VTT from embedded subtitle of House of the Dragon...")
    vtt = await get_or_generate_synced_vtt("series", "tt11198330:1:1", video_url=video_url)
    assert vtt is not None
    print("\n--- SAMPLE TRANSLATED VTT (FIRST 30 LINES) ---")
    print("\n".join(vtt.splitlines()[:30]))
    print("\n--- SAMPLE TRANSLATED VTT (LINES 30-60) ---")
    print("\n".join(vtt.splitlines()[30:60]))

if __name__ == '__main__':
    asyncio.run(test_full_pipeline())
