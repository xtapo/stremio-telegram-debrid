import httpx
from bs4 import BeautifulSoup
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

client = httpx.Client(headers=headers, follow_redirects=True, timeout=15.0)

# 1. Homepage
r = client.get('https://4khdhub.one/')
print('Homepage status:', r.status_code)
soup = BeautifulSoup(r.text, 'html.parser')

# Look at navigation / categories
nav_links = [(a.text.strip(), a['href']) for a in soup.select('nav a, header a, ul.menu a, .nav a') if a.get('href')]
print('\n--- Nav links ---')
for title, href in nav_links[:15]:
    print(f"  {title} -> {href}")

# Look at articles / posts on homepage
articles = soup.select('article, .post-item, .item, .thumb, .entry-title a, .post')
print(f'\n--- Found articles ({len(articles)}) ---')
posts = []
for a in soup.select('article a, .thumb a, .entry-title a, .post a, h2.entry-title a'):
    href = a.get('href', '')
    title = a.get_text(strip=True) or a.get('title', '')
    if href and '4khdhub.one' in href and href != 'https://4khdhub.one/' and href not in [p['href'] for p in posts]:
        # find image if any
        img = a.find('img')
        img_src = img.get('src') or img.get('data-src') if img else None
        posts.append({'title': title, 'href': href, 'img': img_src})

for p in posts[:8]:
    print(f"  Post: {p['title'][:60]} -> {p['href']} (img: {p['img']})")

# 2. Test search
search_query = "avatar"
search_url = f"https://4khdhub.one/?s={search_query}"
print(f'\n--- Testing search: {search_url} ---')
r_s = client.get(search_url)
print('Search status:', r_s.status_code)
soup_s = BeautifulSoup(r_s.text, 'html.parser')
search_results = []
for a in soup_s.select('article a, .thumb a, .entry-title a, .post a, h2.entry-title a, .item a'):
    href = a.get('href', '')
    title = a.get_text(strip=True) or a.get('title', '')
    if href and '4khdhub.one' in href and href != 'https://4khdhub.one/' and href not in [p['href'] for p in search_results]:
        search_results.append({'title': title, 'href': href})
for s in search_results[:5]:
    print(f"  Search result: {s['title']} -> {s['href']}")

# 3. Test detail page if we found post
sample_url = posts[0]['href'] if posts else (search_results[0]['href'] if search_results else None)
if sample_url:
    print(f'\n--- Inspecting detail page: {sample_url} ---')
    r_d = client.get(sample_url)
    soup_d = BeautifulSoup(r_d.text, 'html.parser')
    entry_content = soup_d.select_one('.entry-content, .post-content, article')
    if entry_content:
        # Check download buttons/links
        d_links = entry_content.find_all('a', href=True)
        print(f"Found {len(d_links)} links inside entry content:")
        for dl in d_links:
            print(f"  Link: [{dl.get_text(strip=True)}] -> {dl['href']}")
