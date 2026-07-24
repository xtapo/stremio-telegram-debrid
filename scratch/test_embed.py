import urllib.request
import re
import base64
import json

url = 'https://embed.streamc.xyz/embed.php?hash=30fa9e72a99c1cb3dabdf8a2e4222061'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
html = urllib.request.urlopen(req).read().decode('utf-8')

obf_match = re.search(r'data-obf="([^"]+)"', html)
if obf_match:
    obf = obf_match.group(1)
    d1 = json.loads(base64.b64decode(obf).decode('utf-8'))
    sub_raw = base64.b64decode(d1['sUb']).decode('utf-8')
    sub_json = json.loads(sub_raw)
    print("Decoded sUb:", sub_json)

js_url = 'https://embed.streamc.xyz/player.js?ver=1.8'
js_html = urllib.request.urlopen(urllib.request.Request(js_url, headers={'User-Agent': 'Mozilla/5.0'})).read().decode('utf-8')

# let's look for fetch or POST or api endpoint in js_html
endpoints = re.findall(r'[\'"](/api/[^\'"]+|https?://[^\'"]+)[\'"]', js_html)
print("Endpoints found:", endpoints)
