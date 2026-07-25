import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

url = "https://topxx.vip/api/v1/movies/GzbLQpN8gz"
res = requests.get(url, headers=headers)
print(json.dumps(res.json(), indent=2, ensure_ascii=False))
