import urllib.request
import re

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
url = "https://ernax.pro/assets/index-CzOW_YHx.js"
req = urllib.request.Request(url, headers=headers)
js = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')

# Search for iframe, player, stream, embed, provider patterns
keywords = ['iframe', 'embed', 'player', '/movie/', '/tv/', 'tmdb', 'imdb', 'servers', 'providers']
for kw in ['iframe', 'src=', 'embed', '/watch', 'provider']:
    print(f"=== Keyword: {kw} ===")
    for m in re.finditer(re.escape(kw), js, re.IGNORECASE):
        start = max(0, m.start() - 150)
        end = min(len(js), m.end() + 150)
        chunk = js[start:end]
        if any(w in chunk.lower() for w in ['http', 'stream', 'play', 'movie', 'video', 'watch', 'embed', 'src']):
            print(chunk)
            print("-" * 40)
