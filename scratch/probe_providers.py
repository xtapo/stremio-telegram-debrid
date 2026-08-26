import requests
import json
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

print("=== 1. Testing KKPhim (phimapi.com) ===")
try:
    r = requests.get('https://phimapi.com/v1/api/tim-kiem?keyword=dune', headers=headers, timeout=10)
    print("KKPhim status:", r.status_code)
    data = r.json()
    items = data.get('data', {}).get('items', [])
    print("KKPhim results:", len(items), [it.get('name') for it in items[:3]])
    if items:
        slug = items[0].get('slug')
        r_det = requests.get(f'https://phimapi.com/phim/{slug}', headers=headers, timeout=10)
        det = r_det.json()
        episodes = det.get('episodes', [])
        print("KKPhim ep servers:", len(episodes))
        if episodes and episodes[0].get('server_data'):
            print("KKPhim sample stream:", episodes[0]['server_data'][0].get('link_m3u8') or episodes[0]['server_data'][0].get('link_embed'))
except Exception as e:
    print("KKPhim error:", e)

print("\n=== 2. Testing Anime47 (anime47.love/api or anime47.best) ===")
try:
    r = requests.get('https://anime47.love/api/search?keyword=naruto', headers=headers, timeout=10)
    print("Anime47 status:", r.status_code, r.text[:200])
except Exception as e:
    print("Anime47 error:", e)

print("\n=== 3. Testing RidoMovies (ridomovies.su) ===")
try:
    r = requests.get('https://ridomovies.su/api/search?q=avatar', headers=headers, timeout=10)
    print("RidoMovies status:", r.status_code)
    data = r.json()
    print("RidoMovies results:", len(data.get('data', [])), [it.get('title') for it in data.get('data', [])[:3]])
except Exception as e:
    print("RidoMovies error:", e)

print("\n=== 4. Testing Animehay (ahay.in) ===")
try:
    r = requests.get('https://ahay.in/tim-kiem/naruto', headers=headers, timeout=10)
    print("Animehay status:", r.status_code, "len:", len(r.text))
except Exception as e:
    print("Animehay error:", e)

print("\n=== 5. Testing Animevietsub ===")
try:
    r = requests.get('https://animevietsub.site/tim-kiem/one-piece', headers=headers, timeout=10)
    print("Animevietsub site status:", r.status_code, "len:", len(r.text))
except Exception as e:
    print("Animevietsub error:", e)

print("\n=== 6. Testing PhimHDCS ===")
try:
    r = requests.get('https://phimhdcss.com/api/v1/search?q=dune', headers=headers, timeout=10)
    print("PhimHDCS status:", r.status_code, r.text[:200] if r.status_code == 200 else "")
except Exception as e:
    print("PhimHDCS error:", e)

print("\n=== 7. Testing PhimSea ===")
try:
    r = requests.get('https://phimsea.com/api/titles/search?q=avatar', headers=headers, timeout=10)
    print("PhimSea status:", r.status_code, r.text[:200] if r.status_code == 200 else "")
except Exception as e:
    print("PhimSea error:", e)

print("\n=== 8. Testing Yanhh3d / HoatHinh3D ===")
try:
    r = requests.get('https://hoathinh3d.ad/wp-json/halim/v1/player-key', headers=headers, timeout=10)
    print("HoatHinh3D key status:", r.status_code)
except Exception as e:
    print("HoatHinh3D error:", e)

print("\n=== 9. Testing Anikoto (https://anikototv.to) ===")
try:
    r = requests.get('https://anikototv.to/ajax/search?keyword=solo', headers=headers, timeout=10)
    print("Anikoto status:", r.status_code, r.text[:200] if r.status_code == 200 else "")
except Exception as e:
    print("Anikoto error:", e)
