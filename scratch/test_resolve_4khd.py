import asyncio
import httpx
from bs4 import BeautifulSoup
import re
import urllib.parse

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

async def test_resolve():
    client = httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20.0)
    
    # Let's test a HubCloud link from 4khdhub:
    # E.g. https://hubcloud.ist/drive/7qi5r7qbor1rioq or https://hubcloud.cx/drive/fh8kdejgttc8eh5
    test_urls = [
        "https://hubcloud.ist/drive/7qi5r7qbor1rioq",
        "https://hubcloud.cx/drive/fh8kdejgttc8eh5",
        "https://hubdrive.tips/file/5128031051",
    ]
    
    for url in test_urls:
        print(f"\n============================\nTesting URL: {url}")
        try:
            r = await client.get(url)
            print("Status:", r.status_code, "Final URL:", r.url)
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Print page title and all links
            print("Title:", soup.title.string if soup.title else "")
            links = soup.find_all('a', href=True)
            for a in links:
                h = a['href']
                t = a.get_text(strip=True)
                if any(x in h.lower() for x in ['r2', 'gamerxyt', 'pixel', 'workers', 'download', 'fast', 'cdn', 'stream', 'buzz', 'hubdrive', 'hubcloud']):
                    print(f"   Link: [{t}] -> {h}")
                    
            # If gamerxyt found, let's follow it
            gamer_links = [a['href'] for a in links if 'gamerxyt.com' in a['href'] or 'hubcloud' in a['href'] or 'hubcdn' in a['href']]
            for gl in gamer_links:
                print(f"   Following step 2 -> {gl}")
                r2 = await client.get(gl, headers={'Referer': str(r.url)})
                soup2 = BeautifulSoup(r2.text, 'html.parser')
                print("   Step 2 Title:", soup2.title.string if soup2.title else "")
                for a2 in soup2.find_all('a', href=True):
                    h2 = a2['href']
                    t2 = a2.get_text(strip=True)
                    if any(x in h2.lower() for x in ['r2', 'pixel', 'workers', 'fsl', 'buzz', 'download', 'drive']):
                        print(f"      Stream Link: [{t2}] -> {h2}")
        except Exception as e:
            print("Error:", e)

asyncio.run(test_resolve())
