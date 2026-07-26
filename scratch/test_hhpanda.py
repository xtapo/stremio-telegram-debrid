import sys
import httpx
from bs4 import BeautifulSoup
import re

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://hhpanda.st/"
}

r = httpx.get("https://hhpanda.st/tien-nghich", headers=headers)
soup = BeautifulSoup(r.text, "html.parser")
ep_elements = soup.select(".halim-episode a")
print("BS4 found ep elements:", len(ep_elements))
if ep_elements:
    print("  First ep attrs:", ep_elements[0].attrs)
    print("  First ep text:", ep_elements[0].get_text())

# Print sample HTML snippet of episodes
idx = r.text.find("halim-episode")
print("\nHTML snippet around halim-episode:\n", r.text[max(0, idx-50):min(len(r.text), idx+300)])
