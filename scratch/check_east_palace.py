import sys
sys.stdout.reconfigure(encoding='utf-8')
import httpx
import asyncio
from bs4 import BeautifulSoup

async def check_east_palace():
    hub_url = "https://hubcloud.cx/drive/csf8bibptlniwv1"
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
            print("\nAll download links for East Palace Ep 1 on gamerxyt:")
            for a in soup2.find_all('a', href=True):
                href = a['href']
                text = a.get_text(strip=True)
                if not any(k in href for k in ['snvhost', 'telegram', 'one.one.one.one', 'admin', 'moviesdrives.mov', 'google.com']):
                    print(f" - [{text}] => {href}")

if __name__ == '__main__':
    asyncio.run(check_east_palace())
