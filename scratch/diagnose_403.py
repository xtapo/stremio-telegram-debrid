import sys
sys.stdout.reconfigure(encoding='utf-8')
import httpx
import asyncio
import urllib.parse
from bs4 import BeautifulSoup

async def test_why_403():
    # East Palace Ep 2:
    # HubCloud url: https://hubcloud.cx/drive/pnrnfdyeyyvwwvz
    hub_url = "https://hubcloud.cx/drive/pnrnfdyeyyvwwvz"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp1 = await client.get(hub_url, headers=headers)
        soup1 = BeautifulSoup(resp1.text, 'html.parser')
        gamer_link = None
        for a in soup1.find_all('a', href=True):
            if 'gamerxyt.com' in a['href']:
                gamer_link = a['href']
                break
        print("Gamer link:", gamer_link)
        
        resp2 = await client.get(gamer_link, headers=headers)
        soup2 = BeautifulSoup(resp2.text, 'html.parser')
        
        for a in soup2.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            print(f"\n--- Checking: [{text}] => {href[:80]} ---")
            
            # Test 1: with no referer
            try:
                r_no_ref = await client.get(href, headers={'User-Agent': headers['User-Agent'], 'Range': 'bytes=0-100'})
                print(f"  [No Referer] Status: {r_no_ref.status_code}, Final URL: {str(r_no_ref.url)[:70]}, Type: {r_no_ref.headers.get('content-type')}, Length: {r_no_ref.headers.get('content-length')}")
            except Exception as e:
                print(f"  [No Referer] Error: {e}")
                
            # Test 2: with Referer: https://gamerxyt.com/
            try:
                r_ref = await client.get(href, headers={'User-Agent': headers['User-Agent'], 'Referer': 'https://gamerxyt.com/', 'Range': 'bytes=0-100'})
                print(f"  [With Referer] Status: {r_ref.status_code}, Final URL: {str(r_ref.url)[:70]}, Type: {r_ref.headers.get('content-type')}, Length: {r_ref.headers.get('content-length')}")
            except Exception as e:
                print(f"  [With Referer] Error: {e}")
                
            # If it's pixel / dl.php:
            if 'dl.php?link=' in href or 'pixel.hubcloud.cx' in href or 'gpdl.hubcloud.cx' in href:
                # Extract link param
                parsed = urllib.parse.urlsplit(href)
                params = urllib.parse.parse_qs(parsed.query)
                direct_google = params.get('link', [None])[0]
                if direct_google:
                    print(f"  --> Extracted direct Google link: {direct_google[:70]}")
                    try:
                        r_goog = await client.get(direct_google, headers={'User-Agent': headers['User-Agent'], 'Range': 'bytes=0-100'})
                        print(f"  --> Google link Status: {r_goog.status_code}, Type: {r_goog.headers.get('content-type')}, Length: {r_goog.headers.get('content-length')}, Content-Range: {r_goog.headers.get('content-range')}")
                    except Exception as ge:
                        print(f"  --> Google link Error: {ge}")

if __name__ == '__main__':
    asyncio.run(test_why_403())
