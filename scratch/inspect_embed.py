import urllib.request
import re

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

url = "https://ernax.pro/assets/embedUrl-BbPWPrQg.js"
print(f"Fetching {url}...")
try:
    req = urllib.request.Request(url, headers=headers)
    js = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')
    print("embedUrl chunk length:", len(js))
    print(js)
except Exception as e:
    print("Error:", e)
