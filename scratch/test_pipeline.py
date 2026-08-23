import asyncio
import httpx
from bs4 import BeautifulSoup
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

async def test_full_pipeline():
    client = httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0)
    
    # 1. Search for "Interstellar"
    print("=== Testing Search for 'Interstellar' ===")
    r = await client.get('https://4khdhub.one/?s=Interstellar')
    soup = BeautifulSoup(r.text, 'html.parser')
    cards = soup.select('.movie-card')
    print(f"Found {len(cards)} cards:")
    post_url = None
    for c in cards:
        img = c.find('img')
        title = img.get('alt') if img else c.get_text(strip=True)
        href = c.get('href')
        print(f"   {title} -> {href}")
        if not post_url and href:
            post_url = "https://4khdhub.one" + href if href.startswith('/') else href

    if post_url:
        print(f"\n=== Testing Post Page: {post_url} ===")
        r_post = await client.get(post_url)
        soup_p = BeautifulSoup(r_post.text, 'html.parser')
        
        # Extract download items
        items = soup_p.select('.download-item, .episode-download-item')
        print(f"Found {len(items)} download items:")
        sample_hubcloud = None
        for it in items:
            title_el = it.select_one('.file-title, .episode-file-title, .font-semibold')
            title_txt = title_el.get_text(strip=True) if title_el else ""
            badges = [b.get_text(strip=True) for b in it.select('.badge, .badge-size, .badge-psa')]
            links = [(a.get_text(strip=True), a['href']) for a in it.select('a[href]') if 'hub' in a['href']]
            print(f"   Item: {title_txt[:70]} | Badges: {badges} | Links: {len(links)}")
            if not sample_hubcloud and links:
                for lt, lh in links:
                    if 'hubcloud' in lh:
                        sample_hubcloud = lh
                        break
                        
        if sample_hubcloud:
            print(f"\n=== Testing HubCloud Resolution for: {sample_hubcloud} ===")
            r_hc = await client.get(sample_hubcloud, headers={'Referer': post_url})
            soup_hc = BeautifulSoup(r_hc.text, 'html.parser')
            gamer_link = None
            for a in soup_hc.find_all('a', href=True):
                if 'gamerxyt.com' in a['href']:
                    gamer_link = a['href']
                    break
            print("GamerXYT Link:", gamer_link)
            if gamer_link:
                r_gx = await client.get(gamer_link, headers={'Referer': sample_hubcloud})
                soup_gx = BeautifulSoup(r_gx.text, 'html.parser')
                print("Direct Streams extracted:")
                for a in soup_gx.find_all('a', href=True):
                    h = a['href']
                    t = a.get_text(strip=True).encode('ascii', 'replace').decode('ascii')
                    if any(k in h.lower() for k in ['r2.cloudflarestorage', 'r2.dev', 'gpdl.hubcloud', 'pixeldrain', 'workers.dev']):
                        print(f"   -> [{t}] : {h[:120]}...")

asyncio.run(test_full_pipeline())
