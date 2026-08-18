import asyncio
import re
import urllib.parse
import httpx

async def test_proxy():
    client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)
    
    target_url = "https://moon.peakstorm.top/vd/TG1SakpVOTFhb0RJSGltdXpLeWE4dzpsNlRaRlJmbXVobFpSN0gxb3pldTlLMHB4M1IwWU9zUHpuU3c5R3ZWV01B/index-s2160p-v1-a1.m3u8"
    ref = "https://www.vidking.net/"
    
    # 1. Fetch playlist with Referer
    res = await client.get(target_url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': ref, 'Origin': 'https://www.vidking.net'})
    print("Playlist status with Referer:", res.status_code)
    print("Playlist length:", len(res.text))
    
    # 2. Check first segment URL
    lines = res.text.splitlines()
    for line in lines:
        if 'URI="' in line:
            m = re.search(r'URI="([^"]+)"', line)
            if m:
                init_url = urllib.parse.urljoin(target_url, m.group(1))
                print("\nFound Init Segment URL:", init_url)
                res_init = await client.get(init_url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': ref, 'Origin': 'https://www.vidking.net'})
                print("Init segment status with Referer:", res_init.status_code, "len:", len(res_init.content))
        elif not line.startswith("#") and line.strip():
            chunk_url = urllib.parse.urljoin(target_url, line.strip())
            print("\nFound Video Chunk URL:", chunk_url)
            res_chunk = await client.get(chunk_url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': ref, 'Origin': 'https://www.vidking.net'})
            print("Video chunk status with Referer:", res_chunk.status_code, "len:", len(res_chunk.content))
            break
            
    await client.aclose()

if __name__ == '__main__':
    asyncio.run(test_proxy())
