import httpx
import json
import asyncio

async def test_chunks():
    src_url = "https://moon.peakstorm.top/vd/OXN3d0w5Q1pyVGNmVFNmZFpLeERhQTo0VTdCeWtXM2Q2UEJyb2M5bm91UnhB/index-s1080p-v1-a1.m3u8"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=10.0) as client:
        res = await client.get(src_url)
        print("m3u8 status:", res.status_code)
        m3u8_text = res.text
        print("m3u8 first 500 chars:\n", m3u8_text[:500])
        
        # Test first chunk / init segment
        lines = [l.strip() for l in m3u8_text.splitlines() if l.strip()]
        for l in lines:
            if l.startswith("#EXT-X-MAP:URI="):
                init_url = l.split('URI="')[1].rstrip('"')
                print("\nFetching init map:", init_url)
                r_map = await client.get(init_url)
                print("init map status:", r_map.status_code, "bytes:", len(r_map.content))
            elif not l.startswith("#"):
                seg_url = l
                print("\nFetching media chunk:", seg_url[:100])
                r_seg = await client.get(seg_url)
                print("media chunk status:", r_seg.status_code, "bytes:", len(r_seg.content))
                break

if __name__ == "__main__":
    asyncio.run(test_chunks())
