with open('scratch/film4k_bundle.js', 'r', encoding='utf-8') as f:
    text = f.read()

import re

# find all `tr` occurrences in variable declarations
matches = [m.start() for m in re.finditer(r'\btr\b', text)]
print(f"Total occurrences of 'tr': {len(matches)}")
for m in matches:
    start = max(0, m - 50)
    end = min(len(text), m + 150)
    snippet = text[start:end]
    if any(k in snippet for k in ['lazy', 'import', 'function', '=', '{']):
        print("--- SNIPPET ---")
        print(snippet)
