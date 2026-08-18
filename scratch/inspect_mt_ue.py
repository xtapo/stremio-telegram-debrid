with open("scratch/embedUrl.js", "r", encoding="utf-8") as f:
    code = f.read()

import re
for fn in ['Mt', 'ue']:
    for m in re.finditer(rf'(?:const|let|var|function)\s+{fn}\b[^;{{]+(?:;|\{{[^}}]*\}})', code):
        print(f"--- {fn} ---")
        print(m.group(0))
