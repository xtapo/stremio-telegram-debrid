import hashlib
import urllib.parse
import urllib.request
import re
import json
import base64
import time

user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
embed_url = "https://embed18.streamc.xyz/embed.php?hash=99f386254c018729b4e6a32ac08029f2"

# 1. Fetch fresh embed page
req1 = urllib.request.Request(embed_url, headers={'User-Agent': user_agent, 'Referer': 'https://phim.nguonc.com/'})
html = urllib.request.urlopen(req1).read().decode('utf-8')

# 2. Extract sUb
obf = re.search(r'data-obf="([^"]+)"', html).group(1)
d1 = json.loads(base64.b64decode(obf).decode('utf-8'))
sub_str = d1['sUb']
m3u8_url = f"https://embed18.streamc.xyz/{sub_str}?d=1"

# 3. Fetch fresh M3U8
req2 = urllib.request.Request(m3u8_url, headers={'User-Agent': user_agent, 'Referer': embed_url})
m3u8_text = urllib.request.urlopen(req2).read().decode('utf-8')

# 4. Extract first segment URL
first_segment = None
for line in m3u8_text.splitlines():
    line = line.strip()
    if line and not line.startswith('#'):
        first_segment = urllib.parse.urljoin(m3u8_url, line)
        break

print("First segment URL length:", len(first_segment))

# 5. Fetch first segment directly using original headers
req3 = urllib.request.Request(first_segment, headers={'User-Agent': user_agent, 'Referer': embed_url})
try:
    res3 = urllib.request.urlopen(req3)
    print("DIRECT SEGMENT FETCH SUCCESS! Status:", res3.status, "Bytes:", len(res3.read()))
except Exception as e:
    print("Direct Segment Error:", e)
