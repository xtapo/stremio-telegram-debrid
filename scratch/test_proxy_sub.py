import urllib.request
import urllib.parse
import re
import json
import base64
import sys

sys.stdout.reconfigure(encoding='utf-8')

embed_url = "https://embed14.streamc.xyz/embed.php?hash=1b8f31744ef1d065cd3aaa250c4eb682"
user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# 1. Fetch embed page HTML
req1 = urllib.request.Request(embed_url, headers={
    'User-Agent': user_agent,
    'Referer': 'https://phim.nguonc.com/'
})
html = urllib.request.urlopen(req1).read().decode('utf-8')

# 2. Extract sUb
obf_match = re.search(r'data-obf="([^"]+)"', html)
obf = obf_match.group(1)
d1 = json.loads(base64.b64decode(obf).decode('utf-8'))
sub_str = d1['sUb']
m3u8_url = f"https://embed14.streamc.xyz/{sub_str}?d=1"

# 3. Test Proxying m3u8_url with User-Agent & Referer
req2 = urllib.request.Request(m3u8_url, headers={
    'User-Agent': user_agent,
    'Referer': embed_url
})
res2 = urllib.request.urlopen(req2)
print("Proxy M3U8 Status:", res2.status)
print("Content-Type:", res2.headers.get('Content-Type'))
print("Content length:", len(res2.read()))
