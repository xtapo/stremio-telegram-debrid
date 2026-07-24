import urllib.request
import json
import base64

url = 'https://embed.streamc.xyz/embed.php?hash=30fa9e72a99c1cb3dabdf8a2e4222061'
req = urllib.request.Request(url, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://phim.nguonc.com/'
})
res = urllib.request.urlopen(req)
html = res.read().decode('utf-8')
print("Status:", res.status)

# Also check cookies
cookies = res.headers.get('Set-Cookie')
print("Cookies:", cookies)
