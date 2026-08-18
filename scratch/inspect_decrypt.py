with open("scratch/embedUrl.js", "r", encoding="utf-8") as f:
    code = f.read()

import re

for fn in ['tr', 'sr', 'rr', 'nr']:
    pos = code.find(f"function {fn}(")
    if pos != -1:
        print(f"=== function {fn} ===")
        print(code[pos:pos+1200])
