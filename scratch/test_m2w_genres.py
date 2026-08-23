import httpx
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://movies2watch.vc/'
}

with httpx.Client(headers=headers, follow_redirects=True, timeout=15) as client:
    res = client.get('https://movies2watch.vc/home/')
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # Genres select
    genre_select = soup.select_one('select[name="genre"]')
    if genre_select:
        print("GENRES_MAP = {")
        for opt in genre_select.select('option'):
            if opt.get('value'):
                print(f'    "{opt.text.strip()}": "{opt.get("value")}",')
        print("}")
        
    country_select = soup.select_one('select[name="country"]')
    if country_select:
        print("\nCOUNTRIES_MAP = {")
        for opt in country_select.select('option')[:30]:
            if opt.get('value'):
                print(f'    "{opt.text.strip()}": "{opt.get("value")}",')
        print("}")
