import urllib.request
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://new2.moviesdrive.christmas/'
}

url = "https://mdrive.lol/archive/13164/"
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    print("Status:", resp.status, "Final URL:", resp.geturl())
    html = resp.read().decode('utf-8', errors='ignore')
    soup = BeautifulSoup(html, 'html.parser')
    print("Page Title:", soup.title.string if soup.title else "None")
    for a in soup.find_all('a', href=True):
        print(f"Link: [{a.get_text(strip=True)}] => {a['href']}")
