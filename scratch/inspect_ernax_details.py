import urllib.request
import re

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
url = "https://ernax.pro/assets/index-CzOW_YHx.js"
req = urllib.request.Request(url, headers=headers)
js = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')

# Let's search around stream.ernax.pro
for m in re.finditer(r'stream\.ernax\.pro|bingedframe', js):
    start = max(0, m.start() - 300)
    end = min(len(js), m.end() + 300)
    print("--- MATCH ---")
    print(js[start:end])
    print()
