import httpx
from bs4 import BeautifulSoup
import json
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}
client = httpx.Client(headers=headers, follow_redirects=True, timeout=15.0)

# Let's test search for popular movies/series:
test_searches = ["Avatar", "Deadpool", "Outer Banks", "Game of Thrones", "Loki", "Oppenheimer"]
for query in test_searches:
    url = f"https://4khdhub.one/?s={urllib.parse.quote(query)}" if 'urllib' in locals() else f"https://4khdhub.one/?s={query}"
    r = client.get(url)
    soup = BeautifulSoup(r.text, 'html.parser')
    cards = soup.select('.movie-card, article, div[class*="movie-card"]')
    print(f"\nSearch for '{query}': found {len(cards)} items")
    for c in cards[:4]:
        a = c.find('a', href=True)
        img = c.find('img')
        img_src = img.get('src') if img else None
        title_el = c.find(['h2', 'h3', 'h4', 'div', 'p'], class_=re.compile(r'title|name|movie-card-content', re.I)) or a
        title_text = title_el.get_text(" ", strip=True) if title_el else (a.get_text(" ", strip=True) if a else "")
        # Look for formats/badges
        badges = [b.get_text(strip=True) for b in c.select('.movie-card-formats span, .badge, [class*="format"] span')]
        print(f"  -> Title: {title_text} | Badges: {badges} | Link: {a['href'] if a else None} | Poster: {img_src}")

