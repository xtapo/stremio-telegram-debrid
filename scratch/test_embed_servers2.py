import httpx
from bs4 import BeautifulSoup
import re
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://movies2watch.vc/'
}

with httpx.Client(headers=headers, follow_redirects=True, timeout=15) as client:
    # 1. Videasy: https://player.videasy.to/movie/872585
    r_vde = client.get('https://player.videasy.to/movie/872585')
    print("Videasy status:", r_vde.status_code)
    # Check next.js build and api
    # videasy often has /api/watch or similar Next API routes
    
    # 2. Vidfast: https://vidfast.vc/movie/tt15398776
    r_vdf = client.get('https://vidfast.vc/movie/tt15398776')
    print("Vidfast status:", r_vdf.status_code)
    
    # 3. Let's check other movies on movies2watch.vc
    # Let's search some popular movies: Dune 2, Deadpool, Inside Out 2, Breaking Bad
    for q in ['dune', 'deadpool', 'inside out']:
        res = client.get(f'https://movies2watch.vc/search/{q}')
        soup = BeautifulSoup(res.text, 'html.parser')
        print(f"\n--- Search '{q}' ---")
        for item in soup.select('.flw-item')[:2]:
            a = item.select_one('.film-name a')
            href = a.get('href')
            print("Title:", a.text.strip(), href)
            # get page
            m_res = client.get(href)
            m_pl = re.search(r"const pl_url = ['\"]([^'\"]+)['\"]", m_res.text)
            if m_pl:
                r_pl = client.get(m_pl.group(1), headers={'X-Requested-With': 'XMLHttpRequest', 'Referer': href})
                s_soup = BeautifulSoup(r_pl.text, 'html.parser')
                for srv in s_soup.select('a.sv-item, a[data-srv]'):
                    print("  Server:", srv.get('data-srv'), "URL:", srv.get('data-id'))
