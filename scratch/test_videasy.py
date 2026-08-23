import httpx

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://player.videasy.to/movie/533535',
}

with httpx.Client(headers=headers, follow_redirects=True, timeout=15) as client:
    r = client.get('https://player.videasy.to/_next/static/chunks/pages/movie/%5B...params%5D-af452351ddafbdfb.js')
    print("=== movie chunk content ===")
    print(r.text)
