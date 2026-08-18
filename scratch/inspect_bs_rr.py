with open("scratch/embedUrl.js", "r", encoding="utf-8") as f:
    code = f.read()

import re

for var in ['bs', 'rr', 'Q', 'ms']:
    for m in re.finditer(rf'(?:const|let|var|function)\s+{var}\b[^;{{]+(?:;|\{{[^}}]*\}})', code):
        print(f"--- {var} ---")
        print(m.group(0))
