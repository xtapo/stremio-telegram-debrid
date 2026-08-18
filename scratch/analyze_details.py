import urllib.request
import re

with open("scratch/MovieDetail.js", "r", encoding="utf-8") as f:
    md = f.read()

# Let's find url constructions in MovieDetail.js
print("--- Search for URLs or endpoints in MovieDetail ---")
for m in re.finditer(r'url:\s*([^\n,]+)', md):
    print(m.group(0))

# Let's inspect where Je, Xe, Ze, Ge, Ke etc are defined in MovieDetail
for m in re.finditer(r'const\s+[A-Za-z0-9_]+\s*=\s*(?:Je|Xe|Ze|Ge|Ke|dt|ct|ht|mt|xt|pt|vr|pr|gr|wr|br|yr|kr|jr|Sr|Nr|Lr|Cr)[^;]+;', md):
    print(m.group(0))

# Let's also check SeriesDetail
req = urllib.request.Request("https://ernax.pro/assets/SeriesDetail-x_uxNyRm.js", headers={'User-Agent': 'Mozilla/5.0'})
sd = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')
with open("scratch/SeriesDetail.js", "w", encoding="utf-8") as f:
    f.write(sd)

print("\n--- Search in SeriesDetail ---")
for m in re.finditer(r'url:\s*([^\n,]+)', sd):
    print(m.group(0))
