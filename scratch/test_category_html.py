import urllib.request
from bs4 import BeautifulSoup

def main():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://new2.moviesdrive.christmas/'
    }
    url = "https://new2.moviesdrive.christmas/category/2160p-4k/"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        soup = BeautifulSoup(html, 'html.parser')
        cards = soup.find_all(['div', 'article'], class_=lambda c: c and any(k in str(c) for k in ['post', 'item', 'card', 'poster']))
        print("Found matching container elements:", len(cards))
        for c in cards[:10]:
            a = c.find('a', href=True)
            img = c.find('img')
            title = c.find(['h2', 'h3', 'p', 'span'])
            print(f"Tag: {c.name}, Class: {c.get('class')}")
            if a:
                print(f" -> A: {a.get('href')} | Text: {a.get_text(strip=True)[:40]}")
            if img:
                print(f" -> Img: {img.get('src') or img.get('data-src')}")

if __name__ == '__main__':
    main()
