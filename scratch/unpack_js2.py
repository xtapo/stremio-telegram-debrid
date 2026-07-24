import urllib.request
import re

url = 'https://embed.streamc.xyz/player.js?ver=1.8'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(req).read().decode('utf-8')

for m in re.finditer(r'fetch\(', html):
    start = max(0, m.start() - 200)
    end = min(len(html), m.end() + 200)
    print("Match context:\n", html[start:end])
    print("-" * 50)
