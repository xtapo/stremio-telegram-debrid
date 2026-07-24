import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

test_urls = [
    ("Catalog Phim Mới", "https://vsmov.com/api/danh-sach/phim-moi-cap-nhat?page=1"),
    ("Catalog Phim Lẻ", "https://vsmov.com/api/danh-sach/phim-le?page=1"),
    ("Catalog Phim Bộ", "https://vsmov.com/api/danh-sach/phim-bo?page=1"),
    ("Catalog TV Shows", "https://vsmov.com/api/danh-sach/tv-shows?page=1"),
    ("Catalog Hoạt Hình", "https://vsmov.com/api/danh-sach/hoat-hinh?page=1"),
    ("Search", "https://vsmov.com/api/tim-kiem?keyword=nguoi"),
    ("Genres", "https://vsmov.com/api/the-loai"),
    ("Countries", "https://vsmov.com/api/quoc-gia"),
]

headers = {'User-Agent': 'Mozilla/5.0'}

first_slug = None

for name, url in test_urls:
    try:
        req = urllib.request.Request(url, headers=headers)
        res = urllib.request.urlopen(req, timeout=5)
        text = res.read().decode('utf-8')
        data = json.loads(text)
        status = data.get('status')
        items = data.get('items', [])
        print(f"✅ [{name}] HTTP 200 - status: {status}, items count: {len(items)}")
        if items and not first_slug:
            first_slug = items[0].get('slug')
    except Exception as e:
        print(f"❌ [{name}] {url} => {e}")

if first_slug:
    film_url = f"https://vsmov.com/api/phim/{first_slug}"
    print(f"\nTesting film detail: {film_url}")
    try:
        req = urllib.request.Request(film_url, headers=headers)
        res = urllib.request.urlopen(req, timeout=5)
        data = json.loads(res.read().decode('utf-8'))
        print("Film data keys:", list(data.keys()))
        movie = data.get('movie', {})
        print("Movie title:", movie.get('name'))
        episodes = data.get('episodes', [])
        print("Episodes count:", len(episodes))
        if episodes:
            print("First server name:", episodes[0].get('server_name'))
            server_items = episodes[0].get('server_data', []) or episodes[0].get('items', [])
            print("Server items count:", len(server_items))
            if server_items:
                print("First ep link_m3u8:", server_items[0].get('link_m3u8'))
                print("First ep link_embed:", server_items[0].get('link_embed') or server_items[0].get('embed'))
    except Exception as e:
        print("Error fetching film detail:", e)
