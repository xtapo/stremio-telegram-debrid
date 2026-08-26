import requests
import json

base = "https://phimapi.com"
headers = {'User-Agent': 'Mozilla/5.0'}

print("--- 1. Testing Danh Sách Phim Mới ---")
r = requests.get(f"{base}/danh-sach/phim-moi-cap-nhat?page=1", headers=headers)
data = r.json()
print("Total items:", len(data.get('items', [])))
for it in data.get('items', [])[:3]:
    print(f"  - {it.get('name')} ({it.get('origin_name')}) -> slug: {it.get('slug')}, year: {it.get('year')}")

print("\n--- 2. Testing Danh Sách Phim Lẻ ---")
r = requests.get(f"{base}/v1/api/danh-sach/phim-le?page=1", headers=headers)
data = r.json()
print("Phim Le items:", len(data.get('data', {}).get('items', [])))

print("\n--- 3. Testing Danh Sách Phim Bộ ---")
r = requests.get(f"{base}/v1/api/danh-sach/phim-bo?page=1", headers=headers)
data = r.json()
print("Phim Bo items:", len(data.get('data', {}).get('items', [])))

print("\n--- 4. Testing Danh Sách Hoạt Hình ---")
r = requests.get(f"{base}/v1/api/danh-sach/hoat-hinh?page=1", headers=headers)
data = r.json()
print("Hoat Hinh items:", len(data.get('data', {}).get('items', [])))

print("\n--- 5. Testing Danh Sách TV Shows ---")
r = requests.get(f"{base}/v1/api/danh-sach/tv-shows?page=1", headers=headers)
data = r.json()
print("TV Shows items:", len(data.get('data', {}).get('items', [])))

print("\n--- 6. Testing Search ---")
r = requests.get(f"{base}/v1/api/tim-kiem?keyword=conan&limit=10", headers=headers)
data = r.json()
search_items = data.get('data', {}).get('items', [])
print(f"Search 'conan': {len(search_items)} items")

if search_items:
    slug = search_items[0]['slug']
    print(f"\n--- 7. Testing Detail for {slug} ---")
    r_movie = requests.get(f"{base}/phim/{slug}", headers=headers)
    movie_data = r_movie.json()
    movie = movie_data.get('movie', {})
    print(f"Movie: {movie.get('name')} - {movie.get('origin_name')} - Year: {movie.get('year')}")
    print(f"Poster: {movie.get('poster_url')} | Thumb: {movie.get('thumb_url')}")
    episodes = movie_data.get('episodes', [])
    for ep_grp in episodes:
        print(f"Server Name: {ep_grp.get('server_name')}, Items: {len(ep_grp.get('server_data', []))}")
        if ep_grp.get('server_data'):
            first_ep = ep_grp['server_data'][0]
            print(f"  Ep: {first_ep.get('name')} -> m3u8: {first_ep.get('link_m3u8')}")
