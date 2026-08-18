import httpx
import json
import asyncio

async def test_segments():
    src_url = "https://moon.peakstorm.top/vd/OXN3d0w5Q1pyVGNmVFNmZFpLeERhQTo0VTdCeWtXM2Q2UEJyb2M5bm91UnhB/index-s1080p-v1-a1.m3u8"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.vidking.net/",
        "Origin": "https://www.vidking.net"
    }
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=10.0) as client:
        res = await client.get(src_url)
        print("m3u8 status:", res.status_code)
        
        # Test MAP URI
        lines = [l.strip() for l in res.text.splitlines() if l.strip()]
        for l in lines:
            if l.startswith("#EXT-X-MAP:URI="):
                init_url = l.split('URI="')[1].rstrip('"')
                print("Fetching init MAP:", init_url)
                r_map = await client.get(init_url)
                print("Init map status:", r_map.status_code, "bytes:", len(r_map.content))
            elif not l.startswith("#"):
                seg_url = l
                print("Fetching first media chunk:", seg_url)
                r_seg = await client.get(seg_url)
                print("Media chunk status:", r_seg.status_code, "bytes:", len(r_seg.content), "Content-Type:", r_seg.headers.get("content-type"))
                break

if __name__ == "__main__":
    asyncio.run(test_segments())
