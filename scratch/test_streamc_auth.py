import urllib.request
import urllib.parse
import re
import json
import base64
import sys

sys.stdout.reconfigure(encoding='utf-8')

embed_url = "https://embed14.streamc.xyz/embed.php?hash=1b8f31744ef1d065cd3aaa250c4eb682"
user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# Use CookieJar to handle cookies automatically
import http.cookiejar
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# Step 1: Open embed page with User-Agent & Referer
req1 = urllib.request.Request(embed_url, headers={
    'User-Agent': user_agent,
    'Referer': 'https://phim.nguonc.com/'
})
res1 = opener.open(req1)
html = res1.read().decode('utf-8')

print("Step 1 Embed page status:", res1.status)
print("Cookies received:", [c.name + '=' + c.value for c in cj])

obf_match = re.search(r'data-obf="([^"]+)"', html)
if obf_match:
    obf = obf_match.group(1)
    d1 = json.loads(base64.b64decode(obf).decode('utf-8'))
    sub_str = d1['sUb']
    m3u8_url = f"https://embed14.streamc.xyz/{sub_str}?d=1"
    
    print("\nStep 2 Fetching m3u8:", m3u8_url)
    
    # Try fetching with cookie jar + User-Agent + Referer
    req2 = urllib.request.Request(m3u8_url, headers={
        'User-Agent': user_agent,
        'Referer': embed_url
    })
    try:
        res2 = opener.open(req2)
        print("m3u8 Status:", res2.status)
        content = res2.read().decode('utf-8', errors='ignore')
        print("Content-Type:", res2.headers.get('Content-Type'))
        print("M3U8 snippet:\n", content[:300])
    except Exception as e:
        print("m3u8 fetch error:", e)
