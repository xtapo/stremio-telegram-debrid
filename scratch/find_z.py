with open('scratch/film4k_useData.js', 'r', encoding='utf-8') as f:
    text = f.read()

import re
matches = [m.start() for m in re.finditer(r'function Z\(|var Z\s*=|const Z\s*=', text)]
for m in matches:
    start = max(0, m - 100)
    end = min(len(text), m + 300)
    print("--- Z DEFINITION ---")
    print(text[start:end])
