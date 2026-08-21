with open('scratch/film4k_useData.js', 'r', encoding='utf-8') as f:
    text = f.read()

import re

# let's search for "Q=" or "Q (" or "async function"
matches = [m.start() for m in re.finditer(r'\bQ\s*\(|\bQ\s*=', text)]
for m in matches[:10]:
    start = max(0, m - 50)
    end = min(len(text), m + 150)
    print("--- Q OCCURRENCE ---")
    print(text[start:end])
