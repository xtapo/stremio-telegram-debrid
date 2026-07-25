import sys
import json
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

with open("scratch/topxx_api_doc.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

# Find code blocks or pre tags or JSON samples
pres = soup.find_all(["pre", "code"])
print(f"Found {len(pres)} code/pre tags:")
for i, tag in enumerate(pres):
    print(f"--- BLOCK {i} ---")
    print(tag.text[:500])

