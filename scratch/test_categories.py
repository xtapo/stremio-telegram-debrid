import httpx
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}
client = httpx.Client(headers=headers, follow_redirects=True, timeout=15.0)

test_cats = [
    ("Latest Movies", "https://4khdhub.one/category/movies/"),
    ("4K HDR", "https://4khdhub.one/category/4k-hdr/"),
    ("English Movies", "https://4khdhub.one/category/english-movies/"),
    ("Hindi Movies", "https://4khdhub.one/category/hindi-movies/"),
    ("Web Series", "https://4khdhub.one/category/series/"),
    ("Netflix", "https://4khdhub.one/category/netflix/"),
    ("Anime", "https://4khdhub.one/category/anime/"),
    ("Movies Page 2", "https://4khdhub.one/category/movies/page/2/"),
]

for name, url in test_cats:
    r = client.get(url)
    soup = BeautifulSoup(r.text, 'html.parser')
    cards = soup.select('.movie-card')
    print(f"Category [{name}] ({url}) -> Status: {r.status_code}, Found cards: {len(cards)}")
    if cards:
        first = cards[0]
        img = first.find('img')
        print(f"   Sample: {img.get('alt') if img else 'No img'} -> {first.get('href')}")
