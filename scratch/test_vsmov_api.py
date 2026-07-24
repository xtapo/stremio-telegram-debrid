import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

base_urls = [
    "https://vsmov.com/api/danh-sach/phim-moi-cap-nhat?page=1",
    "https://vsmov.com/api/phim-moi-cap-nhat?page=1",
    "https://vsmov.com/api/home",
    "https://vsmov.com/api/genres",
    "https://vsmov.com/api/countries",
    "https://vsmov.com/api/search?keyword=test",
]

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

for url in base_urls:
    try:
        req = urllib.request.Request(url, headers=headers)
        res = urllib.request.urlopen(req, timeout=5)
        text = res.read().decode('utf-8')
        print(f"SUCCESS {url} => HTTP {res.status}: {text[:150]}")
    except Exception as e:
        print(f"ERROR {url} => {e}")
