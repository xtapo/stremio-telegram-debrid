with open('scratch/film4k_useData.js', 'r', encoding='utf-8') as f:
    text = f.read()

import re

for keyword in ['tvChannels', 'tvEvents', 'tvStream', '/api/tv', '/tv/']:
    matches = [m.start() for m in re.finditer(re.escape(keyword), text)]
    print(f"Keyword: {keyword}, Matches: {len(matches)}")
    for m in matches:
        start = max(0, m - 100)
        end = min(len(text), m + 300)
        print("--- SNIPPET ---")
        print(text[start:end])
        print()
