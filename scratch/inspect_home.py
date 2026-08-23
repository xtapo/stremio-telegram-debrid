from bs4 import BeautifulSoup
import re

with open('scratch/4khdhub_home.html', 'r', encoding='utf-8') as f:
    home_html = f.read()

soup = BeautifulSoup(home_html, 'html.parser')

print("Title:", soup.title.string if soup.title else "No title")

# Find all cards / items
for div in soup.find_all(['div', 'article', 'li']):
    cls = " ".join(div.get('class', []))
    if any(k in cls for k in ['movie', 'item', 'card', 'post', 'grid', 'thumb', 'film', 'col', 'entry']):
        print(f"Found container <{div.name} class='{cls}'> (children: {len(list(div.children))})")
        # print first child text
        txt = div.get_text(strip=True)[:100]
        if txt:
            print("   Content preview:", txt)

print("\n--- ALL A TAGS ---")
for a in soup.find_all('a', href=True):
    href = a['href']
    if not href.startswith('#') and 'category' not in href and href != '/' and not href.endswith('.one/'):
        print(f"A tag: href='{href}' text='{a.get_text(strip=True)[:60]}' img='{a.find('img')}'")
