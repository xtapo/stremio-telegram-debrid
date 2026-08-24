import httpx
import asyncio
import re

async def main():
    headers = {"User-Agent": "Mozilla/5.0"}
    sources = [
        ("Free-TV", "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8"),
        ("YouTube_Moose", "https://raw.githubusercontent.com/benmoose39/YouTube_to_m3u/main/youtube.m3u"),
        ("YouTube_Live", "https://live-iptv.github.io/youtube_live/youtube.m3u"),
        ("IPTV_VN", "https://iptv-org.github.io/iptv/countries/vn.m3u"),
        ("IPTV_US", "https://iptv-org.github.io/iptv/countries/us.m3u"),
    ]
    
    async with httpx.AsyncClient(headers=headers, timeout=10.0, follow_redirects=True) as client:
        for name, url in sources:
            try:
                r = await client.get(url)
                print(f"[{name}] status={r.status_code}, length={len(r.text)}")
                count = len(re.findall(r'#EXTINF:', r.text))
                print(f"[{name}] channels={count}")
                # print first 2 channels
                matches = re.findall(r'#EXTINF:[^\n]+\n[^\n]+', r.text)[:2]
                for m in matches:
                    print("   Example:", m.replace('\n', ' --> '))
            except Exception as e:
                print(f"[{name}] error={e}")

if __name__ == "__main__":
    asyncio.run(main())
