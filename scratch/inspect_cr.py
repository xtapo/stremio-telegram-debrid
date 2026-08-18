with open("scratch/embedUrl.js", "r", encoding="utf-8") as f:
    code = f.read()

import re

# Find function cr definition
pos = code.find("function cr(")
print("Found function cr at:", pos)
# extract next 5000 chars
print(code[pos:pos+5000])
