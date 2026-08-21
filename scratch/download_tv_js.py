import requests
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

tv_js_url = 'https://film4k.net/assets/Tv-CU5WB0Ro.js'
r = requests.get(tv_js_url, headers=headers)
print("Tv JS status:", r.status_code)
print("Tv JS size:", len(r.text))

with open('scratch/film4k_tv_bundle.js', 'w', encoding='utf-8') as f:
    f.write(r.text)

print("Saved scratch/film4k_tv_bundle.js")
