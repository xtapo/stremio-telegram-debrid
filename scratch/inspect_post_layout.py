import httpx
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}
client = httpx.Client(headers=headers, follow_redirects=True, timeout=15.0)

# Fetch movie post
r_m = client.get('https://4khdhub.one/avatar-movie-774/')
with open('scratch/4khd_avatar.html', 'w', encoding='utf-8') as f:
    f.write(r_m.text)

# Fetch series post
r_s = client.get('https://4khdhub.one/outer-banks-series-2214/')
with open('scratch/4khd_outerbanks.html', 'w', encoding='utf-8') as f:
    f.write(r_s.text)

print("Saved avatar and outerbanks pages. Analyzing download blocks...")

soup_m = BeautifulSoup(r_m.text, 'html.parser')
print("\n--- AVATAR POST ---")
print("Title:", soup_m.find(['h1', 'h2']).get_text(strip=True) if soup_m.find(['h1', 'h2']) else "")
# Let's find download sections / blocks
for section in soup_m.select('.download-links, .download-section, .downloads, .entry-content, main, article, div[class*="download"], div[class*="episode"], div[class*="season"]'):
    print("Found section class:", section.get('class'))

# Let's find all download buttons / links and their headings/labels
for a in soup_m.find_all('a', href=True):
    href = a['href']
    if any(h in href for h in ['hubcloud', 'hubdrive', 'gdflix', 'drive', 'download']):
        # Find context (nearest heading, parent text, quality info)
        parent = a.find_parent(['div', 'li', 'p', 'tr'])
        print(f"Movie Download Link: [{a.get_text(strip=True)}] -> {href}")
        if parent:
            print("   Parent context:", " ".join(parent.get_text(" ", strip=True).split())[:120])

soup_s = BeautifulSoup(r_s.text, 'html.parser')
print("\n--- OUTER BANKS SERIES POST ---")
for a in soup_s.find_all('a', href=True):
    href = a['href']
    if any(h in href for h in ['hubcloud', 'hubdrive', 'gdflix', 'drive', 'download']):
        parent = a.find_parent(['div', 'li', 'p', 'tr'])
        print(f"Series Download Link: [{a.get_text(strip=True)}] -> {href}")
        if parent:
            print("   Parent context:", " ".join(parent.get_text(" ", strip=True).split())[:120])
        # Only print first 15 links
