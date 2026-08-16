import sys
sys.stdout.reconfigure(encoding='utf-8')
import urllib.request
import httpx
import asyncio
from bs4 import BeautifulSoup

async def check_all_gamerxyt():
    hub_url = "https://hubcloud.cx/drive/t19altlt1zw1gqk"
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp1 = await client.get(hub_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://hubcloud.cx/'})
        soup1 = BeautifulSoup(resp1.text, 'html.parser')
        gamer_link = None
        for a in soup1.find_all('a', href=True):
            if 'gamerxyt.com' in a['href']:
                gamer_link = a['href']
                break
        print("Gamer link:", gamer_link)
        
        if gamer_link:
            resp2 = await client.get(gamer_link, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': hub_url})
            soup2 = BeautifulSoup(resp2.text, 'html.parser')
            print("\nAll download links on gamerxyt:")
            for a in soup2.find_all('a', href=True):
                href = a['href']
                text = a.get_text(strip=True)
                if not any(k in href for k in ['snvhost', 'telegram', 'one.one.one.one', 'admin', 'moviesdrives.mov']):
                    print(f"\n - [{text}] => {href}")
                    try:
                        import urllib.parse
                        p = urllib.parse.urlsplit(href)
                        clean_path = urllib.parse.quote(p.path)
                        clean_url = urllib.parse.urlunsplit((p.scheme, p.netloc, clean_path, p.query, p.fragment))
                        resp_test = await client.get(clean_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Range': 'bytes=0-100', 'Referer': gamer_link})
                        print(f"    -> Status: {resp_test.status_code}, Final URL: {str(resp_test.url)[:60]}, Type: {resp_test.headers.get('content-type')}, Range: {resp_test.headers.get('content-range')}")
                    except Exception as e:
                        print(f"    -> Test Error: {e}")

if __name__ == '__main__':
    asyncio.run(check_all_gamerxyt())
