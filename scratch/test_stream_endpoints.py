import urllib.request
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://ernax.pro/',
    'Origin': 'https://ernax.pro'
}

endpoints = [
    "https://stream.ernax.pro/stream?type=movie&id=550",
    "https://stream.ernax.pro/ernax2?type=movie&id=550",
    "https://stream.ernax.pro/ernax3?type=movie&id=550",
    "https://stream.ernax.pro/ernax6?type=movie&id=550",
    "https://api.speedracelight.com/seed?mediaId=550"
]

for ep in endpoints:
    print(f"Testing {ep}...")
    try:
        req = urllib.request.Request(ep, headers=headers)
        res = urllib.request.urlopen(req, context=ctx, timeout=10)
        data = res.read().decode('utf-8')
        print(f"Status: {res.status}, Response (first 300 chars): {data[:300]}")
    except Exception as e:
        print(f"Error: {e}")
    print("-" * 50)
