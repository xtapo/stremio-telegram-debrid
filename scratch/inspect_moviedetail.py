import urllib.request
import re

headers = {'User-Agent': 'Mozilla/5.0'}

req = urllib.request.Request("https://ernax.pro/assets/MovieDetail-flPyE0js.js", headers=headers)
content = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')

with open("scratch/MovieDetail.js", "w", encoding="utf-8") as f:
    f.write(content)

print("MovieDetail length:", len(content))
# Find server selection / embed generation logic
for kw in ["server", "stream", "embed", "player", "source"]:
    print(f"=== {kw} in MovieDetail ===")
    for m in re.finditer(re.escape(kw), content, re.IGNORECASE):
        start = max(0, m.start() - 100)
        end = min(len(content), m.end() + 100)
        print(content[start:end])
        print("-" * 30)
