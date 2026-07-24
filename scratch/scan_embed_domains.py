import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

url = 'https://phim.nguonc.com/api/films/phim-moi-cap-nhat?page=1'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
data = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))

embed_domains = set()

for item in data['items']:
    slug = item['slug']
    detail_url = f'https://phim.nguonc.com/api/film/{slug}'
    try:
        detail = json.loads(urllib.request.urlopen(detail_url, timeout=4).read().decode('utf-8'))
        movie = detail.get('movie', {})
        episodes = movie.get('episodes', [])
        for server in episodes:
            for ep in server.get('items', []):
                embed = ep.get('embed', '')
                if embed:
                    domain = embed.split('/')[2] if '/' in embed else embed
                    embed_domains.add(domain)
    except Exception as e:
        pass

print("Unique Embed Domains found across NguonC API:", list(embed_domains))
