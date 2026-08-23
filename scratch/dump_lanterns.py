import httpx
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}
client = httpx.Client(headers=headers, follow_redirects=True, timeout=15.0)

r = client.get('https://4khdhub.one/lanterns-series-7739/')
soup = BeautifulSoup(r.text, 'html.parser')

dl = soup.find('a', href=lambda h: h and 'hubcloud' in h)
if dl:
    p = dl
    for _ in range(4):
        if p.parent:
            p = p.parent
    print(p.prettify()[:2500])
