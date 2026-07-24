import urllib.request
import re

url = 'https://embed14.streamc.xyz/player.js?ver=1.8'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(req).read().decode('utf-8')

for m in re.finditer(r'TextEncoder', html):
    pos = m.start()
    print("Match TextEncoder at pos:", pos)
    print(html[pos-100:pos+300])
    print("=" * 50)
