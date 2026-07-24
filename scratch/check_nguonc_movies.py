import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

url = 'https://phim.nguonc.com/api/films/phim-moi-cap-nhat?page=1'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
data = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))

for item in data['items'][:5]:
    slug = item['slug']
    detail_url = f'https://phim.nguonc.com/api/film/{slug}'
    detail = json.loads(urllib.request.urlopen(detail_url).read().decode('utf-8'))
    movie = detail.get('movie', {})
    print(f"Title: {movie.get('name')} ({movie.get('original_name')})")
    print(f"  Slug: {movie.get('slug')}")
    print(f"  Category: {movie.get('category')}")
    print(f"  Quality: {movie.get('quality')} | Language: {movie.get('language')}")
    print(f"  Poster: {movie.get('poster_url')}")
    episodes = movie.get('episodes', [])
    print(f"  Servers count: {len(episodes)}")
    for server in episodes:
        srv_name = server.get('server_name')
        items = server.get('items', [])
        print(f"    Server '{srv_name}': {len(items)} episodes")
        if items:
            print(f"      Ep 1: name={items[0].get('name')}, embed={items[0].get('embed')}")
    print("-" * 60)
