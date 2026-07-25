import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

base_url = "https://topxx.vip/api/v1"

endpoints = [
    "/movies/latest",
    "/movies/today",
    "/genres",
    "/countries",
    "/movies/search?q=japan"
]

for ep in endpoints:
    url = base_url + ep
    try:
        res = requests.get(url, headers=headers, timeout=10)
        print(f"=== GET {url} (Status {res.status_code}) ===")
        if res.status_code == 200:
            data = res.json()
            print(json.dumps(data, indent=2, ensure_ascii=False)[:1000])
            
            # If movie list returned, fetch single movie detail
            items = []
            if isinstance(data, dict):
                items = data.get("data", []) or data.get("items", []) or data.get("movies", [])
                if isinstance(data, list):
                    items = data
            elif isinstance(data, list):
                items = data
            
            if items and len(items) > 0 and ep == "/movies/latest":
                first_item = items[0]
                code = first_item.get("code") or first_item.get("slug") or first_item.get("id")
                if code:
                    detail_url = f"{base_url}/movies/{code}"
                    print(f"\n--- Testing Detail: {detail_url} ---")
                    d_res = requests.get(detail_url, headers=headers, timeout=10)
                    if d_res.status_code == 200:
                        print(json.dumps(d_res.json(), indent=2, ensure_ascii=False)[:1500])
                    else:
                        print(f"Detail status: {d_res.status_code}")
        else:
            print(res.text[:300])
    except Exception as e:
        print(f"Error: {e}")
    print("\n" + "="*50 + "\n")
