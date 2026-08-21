import re
import json

with open('scratch/film4k_bundle.js', 'r', encoding='utf-8') as f:
    text = f.read()

# Let's find fetch calls or route definitions
# In react-router or similar: path: '/tv', element: ...
# Let's search for '/tv' in the bundle
matches = [m.start() for m in re.finditer(r'/tv', text)]
print(f"Found {len(matches)} occurrences of '/tv'")
for m in matches:
    start = max(0, m - 200)
    end = min(len(text), m + 300)
    print("--- SNIPPET ---")
    print(text[start:end])
    print()
