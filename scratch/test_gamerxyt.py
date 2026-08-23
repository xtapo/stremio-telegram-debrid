import httpx
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Referer': 'https://hubcloud.cx/drive/fh8kdejgttc8eh5'
}
r = httpx.get('https://gamerxyt.com/hubcloud.php?host=hubcloud&id=fh8kdejgttc8eh5&token=MWdvY3BoeEZmS2IzdEhhNFBicys5R00rUjhKaFd5RXFCcWZ3aUtDVzI0QT0=', headers=headers, follow_redirects=True, timeout=10)
soup = BeautifulSoup(r.text, 'html.parser')
for a in soup.find_all('a', href=True):
    txt = a.get_text(strip=True).encode('ascii', 'replace').decode('ascii')
    print(f"[{txt}] --> {a['href']}")
