import urllib.request
import re

url = 'https://embed14.streamc.xyz/player.js?ver=1.8'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(req).read().decode('utf-8')

# Search for web crypto or decrypt terms
crypto_terms = ['subtle', 'decrypt', 'importKey', 'AES', 'GCM', 'SHA', 'digest', 'b65', 'base65', 'iv=']
for term in crypto_terms:
    matches = [m.start() for m in re.finditer(re.escape(term), html, re.IGNORECASE)]
    print(f"Term '{term}': {len(matches)} matches")
    for pos in matches[:3]:
        start = max(0, pos - 100)
        end = min(len(html), pos + 100)
        print("  Context:", repr(html[start:end]))
