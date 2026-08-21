with open('scratch/film4k_bundle.js', 'r', encoding='utf-8') as f:
    text = f.read()

import re

# Find tr definition, e.g. const tr= or function tr
matches = re.finditer(r'(?:const\s+tr\s*=|function\s+tr\s*\()', text)
for m in matches:
    start = max(0, m.start() - 100)
    end = min(len(text), m.start() + 2000)
    print("=== TR DEFINITION ===")
    print(text[start:end])
    print()

# Also find other chunks if tr is lazy loaded (D.lazy)
lazy_matches = re.finditer(r'const\s+tr\s*=\s*(?:D\.lazy|React\.lazy|\(\s*=>\s*import)', text)
for m in lazy_matches:
    start = max(0, m.start() - 100)
    end = min(len(text), m.start() + 500)
    print("=== LAZY TR ===")
    print(text[start:end])
