import urllib.request
import re

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

url = "https://ernax.pro/assets/embedUrl-BbPWPrQg.js"
req = urllib.request.Request(url, headers=headers)
content = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')

with open("scratch/embedUrl.js", "w", encoding="utf-8") as f:
    f.write(content)

print("Saved embedUrl.js, length:", len(content))

# Extract interesting URLs and patterns
urls = set(re.findall(r'https?://[a-zA-Z0-9.\-_/:]+', content))
for u in sorted(urls):
    print("URL:", u)
