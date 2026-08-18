import urllib.request
import re

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

req = urllib.request.Request('https://ernax.pro/', headers=headers)
html = urllib.request.urlopen(req).read().decode('utf-8')
print("HTML length:", len(html))

# find scripts
scripts = re.findall(r'src="(/assets/[^"]+)"', html)
print("Scripts:", scripts)

for s in scripts:
    url = f"https://ernax.pro{s}"
    print(f"Fetching {url}...")
    req = urllib.request.Request(url, headers=headers)
    js = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')
    print(f"Length of {s}: {len(js)}")
    
    # search for api endpoints, embed urls, video providers, m3u8, etc.
    matches = re.findall(r'https?://[a-zA-Z0-9.\-_/]+', js)
    unique_domains = set()
    for m in matches:
        if 'schema.org' not in m and 'w3.org' not in m and 'cloudflare' not in m:
            unique_domains.add(m)
    print("Found URLs in", s, ":", list(unique_domains)[:30])
