import urllib.request
import re

headers = {'User-Agent': 'Mozilla/5.0'}

req = urllib.request.Request("https://ernax.pro/assets/Comments-Bt2aH0qj.js", headers=headers)
content = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')

with open("scratch/Comments.js", "w", encoding="utf-8") as f:
    f.write(content)

print("Comments length:", len(content))

# Look for server list / sources
for kw in ["ernax", "speedracelight", "vidking", "vidlink", "servers", "sources"]:
    print(f"=== {kw} in Comments ===")
    for m in re.finditer(re.escape(kw), content, re.IGNORECASE):
        start = max(0, m.start() - 150)
        end = min(len(content), m.end() + 150)
        print(content[start:end])
        print("-" * 30)
