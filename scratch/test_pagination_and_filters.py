import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Test pagination on /movies/latest
print("=== TESTING PAGINATION ===")
for page in [1, 2, 3]:
    url = f"https://topxx.vip/api/v1/movies/latest?page={page}"
    res = requests.get(url, headers=headers)
    data = res.json().get("data", [])
    print(f"Page {page}: {len(data)} items returned. First title: {data[0]['trans'][0]['title'] if data else 'None'}")

# Test Genre endpoint: Hentai 18+ (code NqlIpFB5ov)
print("\n=== TESTING GENRE ENDPOINT ===")
url_g = "https://topxx.vip/api/v1/genres/NqlIpFB5ov/movies?page=1"
res_g = requests.get(url_g, headers=headers)
data_g = res_g.json().get("data", [])
print(f"Genre Hentai (NqlIpFB5ov): {len(data_g)} items returned.")

# Test Country endpoint: Japan (code jp)
print("\n=== TESTING COUNTRY ENDPOINT ===")
url_c = "https://topxx.vip/api/v1/countries/jp/movies?page=1"
res_c = requests.get(url_c, headers=headers)
data_c = res_c.json().get("data", [])
print(f"Country Japan (jp): {len(data_c)} items returned.")
