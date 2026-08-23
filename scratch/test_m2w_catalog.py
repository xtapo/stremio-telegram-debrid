import httpx
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://movies2watch.vc/'
}

with httpx.Client(headers=headers, follow_redirects=True, timeout=15) as client:
    pages = [
        'https://movies2watch.vc/home/',
        'https://movies2watch.vc/movies/',
        'https://movies2watch.vc/movies?page=2',
        'https://movies2watch.vc/movies?page=3',
        'https://movies2watch.vc/tv-series/',
        'https://movies2watch.vc/tv-series?page=2',
        'https://movies2watch.vc/search/action',
    ]
    for p in pages:
        r = client.get(p)
        s = BeautifulSoup(r.text, 'html.parser')
        items = s.select('.flw-item')
        print(f"Page {p} -> {r.status_code}, items found: {len(items)}")
        if items:
            first = items[0].select_one('.film-name a')
            poster = items[0].select_one('.film-poster-img')
            info = items[0].select_one('.film-infor')
            print(f"   Sample item: {first.text.strip() if first else ''}")
            print(f"   Href: {first.get('href') if first else ''}")
            print(f"   Poster: {poster.get('src') or poster.get('data-src') if poster else ''}")
            print(f"   Info: {info.text.strip() if info else ''}")
            
    # Also check filter form
    res_home = client.get('https://movies2watch.vc/home/')
    s_home = BeautifulSoup(res_home.text, 'html.parser')
    filter_form = s_home.select_one('form#m2wFilterForm, form[action*="filter"]')
    if filter_form:
        print("\nFilter form action:", filter_form.get('action'))
        # find selects / inputs
        for inp in filter_form.select('input, select'):
            print(" - Filter input:", inp.get('name'), inp.get('type'), inp.get('value'), [o.get('value') for o in inp.select('option')])
