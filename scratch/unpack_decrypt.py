import urllib.request
import re

url = 'https://embed14.streamc.xyz/player.js?ver=1.8'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(req).read().decode('utf-8')

pos = html.find('decryptM3U8')
if pos != -1:
    start = max(0, pos - 200)
    end = min(len(html), pos + 2500)
    print(html[start:end])
