with open("scratch/embedUrl.js", "r", encoding="utf-8") as f:
    code = f.read()

import re

# Find functions, objects, servers
for kw in ["stream.ernax.pro", "speedracelight", "vidapi", "vidking", "vidlink", "videasy", "moviesapi", "vidnest"]:
    print(f"=== SEARCH: {kw} ===")
    for m in re.finditer(re.escape(kw), code):
        start = max(0, m.start() - 250)
        end = min(len(code), m.end() + 250)
        print(code[start:end])
        print("=" * 40)
