import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

res_g = requests.get("https://topxx.vip/api/v1/genres", headers=headers)
print("=== GENRES ===")
for g in res_g.json().get("data", []):
    code = g.get("code")
    slug = g.get("slug")
    names = [t.get("name") for t in g.get("translations", [])]
    print(f"Code: {code} | Slug: {slug} | Names: {names}")

print("\n=== COUNTRIES ===")
res_c = requests.get("https://topxx.vip/api/v1/countries", headers=headers)
for c in res_c.json().get("data", []):
    code = c.get("code")
    slug = c.get("slug")
    names = [t.get("name") for t in c.get("translations", [])]
    print(f"Code: {code} | Slug: {slug} | Names: {names}")
