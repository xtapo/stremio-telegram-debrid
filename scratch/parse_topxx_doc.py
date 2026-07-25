import sys
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

res = requests.get("https://topxx.vip/api", headers=headers, timeout=10)
res.encoding = 'utf-8'

with open("scratch/topxx_api_doc.html", "w", encoding="utf-8") as f:
    f.write(res.text)

soup = BeautifulSoup(res.text, "html.parser")
print("TITLE:", soup.title.string if soup.title else "")

text = soup.get_text(separator="\n")
lines = [line.strip() for line in text.splitlines() if line.strip()]

# Save extracted text documentation
with open("scratch/topxx_api_doc.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("\n--- FIRST 150 LINES OF DOC ---")
print("\n".join(lines[:150]))
