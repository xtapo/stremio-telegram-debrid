from bs4 import BeautifulSoup

with open('scratch/4khdhub_home.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

cats = []
for a in soup.find_all('a', href=True):
    href = a['href']
    if 'category' in href or 'genre' in href or 'type' in href:
        cats.append((a.get_text(strip=True), href))

print("Found category links on 4khdhub:")
for text, href in set(cats):
    print(f"  {text} -> {href}")
