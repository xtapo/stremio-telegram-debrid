import httpx
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}
client = httpx.Client(headers=headers, follow_redirects=True, timeout=15.0)
r = client.get('https://4khdhub.one/')
with open('scratch/4khdhub_home.html', 'w', encoding='utf-8') as f:
    f.write(r.text)

r_s = client.get('https://4khdhub.one/?s=avatar')
with open('scratch/4khdhub_search.html', 'w', encoding='utf-8') as f:
    f.write(r_s.text)

print("Saved home and search HTML. Now parsing structure...")
soup = BeautifulSoup(r.text, 'html.parser')
# Find main content container
main = soup.find('main') or soup.find('div', id='content') or soup.find('div', class_='content') or soup.find('body')
print("Top-level tags in body/main:")
if main:
    for child in main.find_all(recursive=False):
        print(f"Tag: {child.name}, class: {child.get('class')}, id: {child.get('id')}")

# Find all <a> tags that look like movie posts
for a in soup.find_all('a'):
    href = a.get('href', '')
    if href and href.startswith('https://4khdhub.one/') and not href.endswith(('.css', '.js', '.png', '.jpg', '/')) and 'category' not in href and 'page' not in href:
        print("Candidate post link:", href, "Text:", a.get_text(strip=True)[:50])
