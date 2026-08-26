import json
import requests
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://ridomovies.su/'
}

print("=== Testing RidoMovies Detail & Stream ===")
try:
    r = requests.get('https://ridomovies.su/api/search?q=avatar', headers=headers, timeout=10)
    data = r.json()
    item = data['data'][0]
    print("Found item:", item['title'], item['slug'])
    # Check item detail page
    slug = item['slug']
    page_r = requests.get(f'https://ridomovies.su/movies/{slug}', headers=headers, timeout=10)
    print("Page status:", page_r.status_code, "len:", len(page_r.text))
    # Look for iframe / player / core api in ridomovies
    iframe_matches = re.findall(r'src=["\']([^"\']*embed[^"\']*)["\']', page_r.text, re.IGNORECASE)
    print("Iframe matches:", iframe_matches)
except Exception as e:
    print("RidoMovies error:", e)

print("\n=== Testing KKPhim Detail & Stream ===")
try:
    r = requests.get('https://phimapi.com/v1/api/tim-kiem?keyword=mai', headers=headers, timeout=10)
    data = r.json()
    items = data.get('data', {}).get('items', [])
    print(f"KKPhim found {len(items)} items")
    if items:
        item = items[0]
        print("First item:", item.get('name'), "slug:", item.get('slug'))
        r_det = requests.get(f"https://phimapi.com/phim/{item.get('slug')}", headers=headers, timeout=10)
        det = r_det.json()
        episodes = det.get('episodes', [])
        for ep_group in episodes:
            server_name = ep_group.get('server_name')
            print(f"Server: {server_name}, Ep count: {len(ep_group.get('server_data', []))}")
            if ep_group.get('server_data'):
                first_ep = ep_group['server_data'][0]
                print(f"  Ep {first_ep.get('name')}: m3u8={first_ep.get('link_m3u8')}")
except Exception as e:
    print("KKPhim error:", e)
