import httpx
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}
client = httpx.Client(headers=headers, follow_redirects=True, timeout=15.0)

for u in ['https://4khdhub.one/lanterns-series-7739/', 'https://4khdhub.one/sx-aka-sandx-series-7789/']:
    r = client.get(u)
    soup = BeautifulSoup(r.text, 'html.parser')
    print(f"\n--- URL: {u} ---")
    items = soup.select('.download-item')
    for item in items[:6]:
        ep = item.select_one('.episode-number')
        hdr = item.select_one('.download-header .font-semibold')
        file_t = item.select_one('.file-title')
        links = [(a.get_text(strip=True), a['href']) for a in item.select('a[href]')]
        print(f"   Ep tag: {ep.get_text(strip=True) if ep else 'None'} | Header: {hdr.get_text(' ', strip=True)[:50] if hdr else ''}")
        print(f"     File: {file_t.get_text(strip=True) if file_t else ''}")
        print(f"     Links: {links}")
