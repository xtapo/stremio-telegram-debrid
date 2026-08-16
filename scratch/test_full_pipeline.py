import asyncio
import httpx
import re
import urllib.parse
import json
import html
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://new2.moviesdrive.christmas/'
}

async def search_moviesdrive(query: str, page: int = 1):
    url = f"https://new2.moviesdrive.christmas/search.php?q={urllib.parse.quote(query)}&page={page}"
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=HEADERS)
        if resp.status_code == 200:
            return resp.json()
        return {}

async def resolve_hubcloud_links(post_url: str):
    """From a post page on moviesdrive, extract hubcloud search-recover links."""
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(post_url, headers=HEADERS)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, 'html.parser')
        content = soup.find('div', class_='entry-content') or soup.find('article') or soup
        results = []
        for a in content.find_all('a', href=True):
            href = a.get('href', '')
            text = a.get_text(strip=True)
            if 'hubcloud' in href:
                results.append({'text': text, 'url': href})
        return results

async def resolve_hubcloud_files(hubcloud_url: str):
    """From a hubcloud search-recover url, query the search API to get individual file links."""
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(hubcloud_url, headers={'User-Agent': HEADERS['User-Agent'], 'Referer': 'https://new2.moviesdrive.christmas/'})
        page_html = resp.text
        final_url = str(resp.url)
        
        q_match = re.search(r'const Q_INITIAL\s*=\s*"([^"]+)"', page_html)
        token_match = re.search(r'const FROM_AC_TOKEN\s*=\s*"([^"]+)"', page_html)
        
        if not token_match:
            return []
            
        token_val = token_match.group(1)
        q_val = q_match.group(1) if q_match else ""
        # decode escapes and html entities
        try:
            q_val = q_val.encode('utf-8').decode('unicode-escape')
        except Exception:
            pass
        q_val = html.unescape(q_val)
        # clean query for best search match
        clean_q = re.sub(r'[\r\n\t]', ' ', q_val).strip()
        
        api_url = f"https://hubcloud.cx/drive/search-recover.php?api=search&q={urllib.parse.quote(clean_q)}&page=1&from_ac={token_val}"
        api_resp = await client.get(api_url, headers={'User-Agent': HEADERS['User-Agent'], 'Referer': final_url, 'Accept': 'application/json'})
        if api_resp.status_code == 200:
            data = api_resp.json()
            return data.get('hits', [])
        return []

async def resolve_direct_stream(hubcloud_file_url: str):
    """Given https://hubcloud.cx/drive/{id}, resolve to direct stream URL."""
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        # Step 1: get gamerxyt link
        resp1 = await client.get(hubcloud_file_url, headers={'User-Agent': HEADERS['User-Agent'], 'Referer': 'https://hubcloud.cx/'})
        soup1 = BeautifulSoup(resp1.text, 'html.parser')
        gamer_link = None
        for a in soup1.find_all('a', href=True):
            if 'gamerxyt.com' in a['href']:
                gamer_link = a['href']
                break
        if not gamer_link:
            return None
            
        # Step 2: fetch gamerxyt page
        resp2 = await client.get(gamer_link, headers={'User-Agent': HEADERS['User-Agent'], 'Referer': hubcloud_file_url})
        soup2 = BeautifulSoup(resp2.text, 'html.parser')
        
        streams = []
        for a in soup2.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            if 'workers.dev' in href or 'video-downloads.googleusercontent.com' in href or 'pixel.hubcloud.cx' in href or 'dl.php?link=' in href:
                streams.append({'type': text, 'url': href})
                
        return streams

async def main():
    print("--- Testing Search ---")
    data = await search_moviesdrive("Inception")
    hits = data.get('hits', [])
    print(f"Found {len(hits)} hits for Inception")
    if not hits:
        return
    
    first = hits[0]['document']
    print(f"Title: {first.get('post_title')} | URL: {first.get('permalink')}")
    full_post_url = "https://new2.moviesdrive.christmas" + first.get('permalink')
    
    print("\n--- Testing Extract Hubcloud Links ---")
    hc_links = await resolve_hubcloud_links(full_post_url)
    print(f"Found {len(hc_links)} HubCloud buttons:")
    for h in hc_links[:5]:
        print(f" - [{h['text']}] => {h['url']}")
        
    if hc_links:
        print("\n--- Testing HubCloud File Resolution ---")
        files = await resolve_hubcloud_files(hc_links[0]['url'])
        print(f"Found {len(files)} files:")
        for f in files[:3]:
            print(f" - File: {f.get('file_name')} ({f.get('size')}) => {f.get('url')}")
            
        if files:
            print("\n--- Testing Direct Stream Resolution ---")
            streams = await resolve_direct_stream(files[0]['url'])
            print(f"Found {len(streams) if streams else 0} direct stream links:")
            if streams:
                for s in streams:
                    print(f" - [{s['type']}] => {s['url']}")

if __name__ == '__main__':
    asyncio.run(main())
