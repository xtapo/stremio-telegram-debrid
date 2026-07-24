import urllib.request
import re

url = 'https://embed14.streamc.xyz/player.js?ver=1.8'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(req).read().decode('utf-8')

pos = html.find('AES-GCM')
if pos == -1:
    pos = html.find('importKey')
if pos != -1:
    print(html[pos-300:pos+500])
