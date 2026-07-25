import requests
import json

urls_to_test = [
    "https://topxx.vip/api",
    "https://topxx.vip/api/v1",
    "https://topxx.vip/api.php",
    "https://topxx.vip/api/danh-sach/phim-moi-cap-nhat",
    "https://topxx.vip/api/v1/danh-sach/phim-moi-cap-nhat",
    "https://topxx.vip"
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

for url in urls_to_test:
    try:
        res = requests.get(url, headers=headers, timeout=10)
        print(f"URL: {url} -> Status: {res.status_code}")
        print(f"Content-Type: {res.headers.get('content-type')}")
        snippet = res.text[:300].replace('\n', ' ')
        print(f"Snippet: {snippet}\n")
    except Exception as e:
        print(f"URL: {url} -> Error: {e}\n")
