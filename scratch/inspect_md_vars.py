with open("scratch/MovieDetail.js", "r", encoding="utf-8") as f:
    md = f.read()

import re

# Find definitions around Je, Xe, Ze, Ge, Ke, etc.
for m in re.finditer(r'([A-Za-z0-9_$]+)\s*=\s*(?:dt|ct|ht|mt|xt|pt|vr|pr|gr|wr|br|yr|kr|jr|Sr|Nr|Lr|Cr)\([^)]*\)', md):
    print(m.group(0))

print("\n--- Let's look around 'streamEndpoint' in MovieDetail ---")
for m in re.finditer(r'streamEndpoint', md):
    start = max(0, m.start() - 200)
    end = min(len(md), m.end() + 200)
    print(md[start:end])
    print("=" * 40)
