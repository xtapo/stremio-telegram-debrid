with open('scratch/film4k_useData.js', 'r', encoding='utf-8') as f:
    text = f.read()

import re
matches = [m.start() for m in re.finditer(r'function Q\(|const Q\s*=', text)]
for m in matches:
    start = max(0, m - 100)
    end = min(len(text), m + 300)
    print("--- Q DEFINITION ---")
    print(text[start:end])
