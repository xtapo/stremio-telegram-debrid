import urllib.request
import json
import base64
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

embed_url = 'https://embed14.streamc.xyz/embed.php?hash=1b8f31744ef1d065cd3aaa250c4eb682'
req = urllib.request.Request(embed_url, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://phim.nguonc.com/'
})
res = urllib.request.urlopen(req)
html = res.read().decode('utf-8')

obf_match = re.search(r'data-obf="([^"]+)"', html)
if obf_match:
    obf = obf_match.group(1)
    d1 = json.loads(base64.b64decode(obf).decode('utf-8'))
    sub_str = d1['sUb']
    print("sUb string:", sub_str)
    
    stream_path = f"https://embed14.streamc.xyz/{sub_str}?d=1"
    print("Trying stream path:", stream_path)
    
    try:
        req2 = urllib.request.Request(stream_path, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': embed_url
        })
        res2 = urllib.request.urlopen(req2)
        print("Status:", res2.status)
        print("Content-Type:", res2.headers.get('Content-Type'))
        content = res2.read()
        print("Length:", len(content))
        print("Preview:", content[:400].decode('utf-8', errors='ignore'))
    except Exception as e:
        print("Error fetching stream path:", e)
