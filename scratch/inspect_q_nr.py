with open("scratch/embedUrl.js", "r", encoding="utf-8") as f:
    code = f.read()

import re

# Find definition of Q in embedUrl.js
for m in re.finditer(r'const\s+Q\s*=\s*[^;]+;', code):
    print(m.group(0))

# Find nr function (speedracelight)
pos = code.find("function nr(")
if pos != -1:
    print("function nr:", code[pos:pos+1500])
