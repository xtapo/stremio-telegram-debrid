import httpx
from bs4 import BeautifulSoup
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://movies2watch.vc/'
}

with httpx.Client(headers=headers, follow_redirects=True, timeout=15) as client:
    ep_url = 'https://movies2watch.vc/series/avatar-the-last-airbender-67006/1-1/'
    r = client.get(ep_url)
    print("Episode page status:", r.status_code)
    m = re.search(r"const pl_url = ['\"]([^'\"]+)['\"]", r.text)
    if m:
        print("Episode page pl_url:", m.group(1))
        r_pl = client.get(m.group(1), headers={'X-Requested-With': 'XMLHttpRequest', 'Referer': ep_url})
        print("Episode pl_url response snippet:", r_pl.text[:300])
        soup_pl = BeautifulSoup(r_pl.text, 'html.parser')
        for srv in soup_pl.select('a.sv-item, a[data-srv]'):
            print(" * Server:", srv.get('data-srv'), "URL/data-id:", srv.get('data-id'), "title:", srv.get('title'))
    else:
        print("pl_url not found in episode page")
