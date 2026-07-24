import urllib.request
import re

url = 'https://embed.streamc.xyz/player.js?ver=1.8'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(req).read().decode('utf-8')

all_q = re.findall(r"'([^'\\]{2,80})'", html)
print("Found quotes:", len(all_q))
for s in all_q:
    if any(kw in s.lower() for kw in ['http', 'm3u8', 'stream', 'fetch', 'post', 'get', 'json', 'api', 'player', '.php', 'key', 'hash', 'url', 'hls']):
        print("  ->", s)
