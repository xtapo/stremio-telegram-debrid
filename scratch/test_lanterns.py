import httpx
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}
client = httpx.Client(headers=headers, follow_redirects=True, timeout=15.0)

r = client.get('https://4khdhub.one/lanterns-series-7739/')
soup = BeautifulSoup(r.text, 'html.parser')
print("Status:", r.status_code)
print("Title:", soup.find('h1'))
# Check any links or text in body
for a in soup.find_all('a', href=True):
    if not a['href'].startswith(('#', '/', 'https://4khdhub.one')):
        print("External link:", a.get_text(strip=True), "->", a['href'])
print("Page text snippet:", soup.get_text(" ", strip=True)[:500])
