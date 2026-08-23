import httpx
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}
client = httpx.Client(headers=headers, follow_redirects=True, timeout=15.0)

r = client.get('https://4khdhub.one/category/series/')
soup = BeautifulSoup(r.text, 'html.parser')
cards = soup.select('.movie-card')
print("Series on /category/series/:")
for c in cards[:6]:
    href = c['href']
    title = c.find('img').get('alt', '') if c.find('img') else href
    print(f"  {title} -> https://4khdhub.one{href}")
    
# Inspect one of the newest series
if cards:
    test_url = "https://4khdhub.one" + cards[0]['href']
    r_detail = client.get(test_url)
    soup_d = BeautifulSoup(r_detail.text, 'html.parser')
    print(f"\nInspecting newest series: {test_url}")
    items = soup_d.select('.download-item')
    for item in items[:8]:
        ep = item.select_one('.episode-number')
        hdr = item.select_one('.download-header .font-semibold')
        file_t = item.select_one('.file-title')
        print(f"   Ep tag: {ep.get_text(strip=True) if ep else 'None'} | Header: {hdr.get_text(' ', strip=True)[:60] if hdr else ''} | File: {file_t.get_text(strip=True)[:60] if file_t else ''}")

