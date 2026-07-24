import urllib.request
import re

url = 'https://embed.streamc.xyz/player.js?ver=1.8'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(req).read().decode('utf-8')

# Search for occurrences of 'h' or 't' or dataset or POST in player.js
matches = [m.start() for m in re.finditer(r'sUb|streamData|\.h|\.t', html)]
print("Total occurrences:", len(matches))

for pos in matches[:10]:
    start = max(0, pos - 150)
    end = min(len(html), pos + 150)
    print("Context around match:")
    print(html[start:end])
    print("=" * 40)
