with open("scratch/embedUrl.js", "r", encoding="utf-8") as f:
    code = f.read()

import re

# Find exports at the end of embedUrl.js
print("Exports:", code[-300:])

# Search for the function definitions of dt, ct, ht, mt, xt, pt etc.
for fn in ['pr', 'vr', 'gr', 'wr', 'br', 'yr', 'kr', 'jr', 'Sr', 'Nr', 'Lr', 'Cr']:
    for m in re.finditer(rf'function\s+{fn}\b[^}}]+\}}', code):
        print(m.group(0))

print("=" * 50)
# Also look at the Custom Player / Stream player component in embedUrl.js
# What is the component that uses `streamEndpoint`?
for m in re.finditer(r'streamEndpoint', code):
    start = max(0, m.start() - 200)
    end = min(len(code), m.end() + 500)
    print(code[start:end])
    print("-" * 50)
