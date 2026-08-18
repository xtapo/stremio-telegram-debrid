with open("scratch/MovieDetail.js", "r", encoding="utf-8") as f:
    md = f.read()

import re

# Find imports in MovieDetail
print(md[:600])

# Find how Je, Xe, Ze, Ge, Ke are defined in MovieDetail
for var in ['Je', 'Xe', 'Ze', 'Ge', 'Ke']:
    for m in re.finditer(rf'\b{var}\s*=', md):
        start = max(0, m.start() - 50)
        end = min(len(md), m.end() + 150)
        print(f"--- Var {var} ---")
        print(md[start:end])
