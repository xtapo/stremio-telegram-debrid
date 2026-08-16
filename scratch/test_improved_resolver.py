import sys
sys.stdout.reconfigure(encoding='utf-8')
import httpx
import asyncio
from bs4 import BeautifulSoup
import urllib.parse
import re

async def resolve_direct_stream_links_improved(hubcloud_file_url: str):
    streams = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://hubcloud.cx/'
    }
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        # Step 1: fetch HubCloud drive page
        resp1 = await client.get(hubcloud_file_url, headers=headers)
        soup1 = BeautifulSoup(resp1.text, 'html.parser')
        gamer_link = None
        for a in soup1.find_all('a', href=True):
            if 'gamerxyt.com' in a['href']:
                gamer_link = a['href']
                break
        if not gamer_link:
            return []
            
        # Step 2: fetch gamerxyt page
        resp2 = await client.get(gamer_link, headers={**headers, 'Referer': hubcloud_file_url})
        soup2 = BeautifulSoup(resp2.text, 'html.parser')
        
        for a in soup2.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            
            # 1. Cloudflare R2 direct stream link
            if 'r2.cloudflarestorage.com' in href or 'cloudflarestorage.com' in href:
                streams.append({'type': '⚡ FSL Server (Cloudflare R2)', 'url': href})
            
            # 2. Cloudflare Workers stream link
            elif 'workers.dev' in href:
                p = urllib.parse.urlsplit(href)
                clean_path = urllib.parse.quote(p.path)
                clean_url = urllib.parse.urlunsplit((p.scheme, p.netloc, clean_path, p.query, p.fragment))
                streams.append({'type': '⚡ Fast Worker CDN', 'url': clean_url})
                
            # 3. Pixeldrain link
            elif 'pixeldrain' in href:
                m = re.search(r'/u/([a-zA-Z0-9]+)', href)
                if m:
                    pd_id = m.group(1)
                    streams.append({'type': '🚀 Pixeldrain Stream', 'url': f"https://pixeldrain.com/api/file/{pd_id}"})
                    
    return streams

async def main():
    print("Testing East Palace Ep 1:")
    s1 = await resolve_direct_stream_links_improved("https://hubcloud.cx/drive/csf8bibptlniwv1")
    for s in s1:
        print(f" -> [{s['type']}] => {s['url'][:100]}...")
        
    print("\nTesting Spooky in Love Ep 1:")
    s2 = await resolve_direct_stream_links_improved("https://hubcloud.cx/drive/t19altlt1zw1gqk")
    for s in s2:
        print(f" -> [{s['type']}] => {s['url'][:100]}...")

if __name__ == '__main__':
    asyncio.run(main())
