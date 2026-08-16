import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
from config import Config
from subtitles_service import get_or_generate_synced_vtt, CACHE_DIR

async def test():
    item_id = "tt11198330:1:3"
    print(f"Testing get_or_generate_synced_vtt for {item_id}...")
    vtt = await get_or_generate_synced_vtt("series", item_id)
    if vtt:
        lines = vtt.splitlines()
        print(f"Total lines returned: {len(lines)}")
        print("\n--- SAMPLE LINES ---")
        print("\n".join(lines[:35]))
        
        cache_path = os.path.join(CACHE_DIR, f"vi_sync_tt11198330_1_3.vtt")
        print(f"\nCache file exists: {os.path.exists(cache_path)} (Size: {os.path.getsize(cache_path)} bytes)")
    else:
        print("Failed to generate VTT!")

if __name__ == '__main__':
    asyncio.run(test())
