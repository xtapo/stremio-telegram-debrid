import requests
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

js_url = 'https://film4k.net/assets/index-Xej_h4s6.js'
r = requests.get(js_url, headers=headers)
print("JS size:", len(r.text))

with open('scratch/film4k_bundle.js', 'w', encoding='utf-8') as f:
    f.write(r.text)

# Search for /api/ or tv endpoints or channels
endpoints = set(re.findall(r'["\'](/api/[^"\']+)["\']', r.text))
print("Found API endpoints:")
for ep in sorted(endpoints):
    print(" ", ep)

# Search for tv or channel references
tv_matches = set(re.findall(r'["\']([^"\']*(?:tv|channel|m3u8|stream)[^"\']*)["\']', r.text, re.IGNORECASE))
print("\nTV related strings (sample of 20):")
for s in list(tv_matches)[:20]:
    print(" ", s)
