import re
import requests

html = open('scratch/yanhh_sample.html', encoding='utf-8').read()
card_blocks = re.findall(r'<div class="flw-item">([\s\S]*?)(?=<div class="flw-item"|</div>\s*<div class="clearfix">|<div class="pre-pagination)', html)
print("Card blocks found:", len(card_blocks))
for b in card_blocks[:5]:
    href_m = re.search(r'<a[^>]+href=["\']([^"\']+)["\']', b)
    title_m = re.search(r'<h3 class="film-name">[\s\S]*?<a[^>]*>([^<]+)</a>', b)
    img_m = re.search(r'<img[^>]+(?:data-src|src)=["\']([^"\']+)["\']', b)
    print("  Card:", title_m.group(1).strip() if title_m else "No title", "->", href_m.group(1) if href_m else "", "Img:", img_m.group(1) if img_m else "")

# Also test Rido with httpx
import httpx
import asyncio

async def test_rido_httpx():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://ridomovies.su/",
        "Origin": "https://ridomovies.su"
    }
    # In httpx, HTTP2 or default headers
    async with httpx.AsyncClient(headers=headers, http2=False, timeout=10.0) as client:
        r = await client.get("https://ridomovies.su/api/search?q=avatar")
        print("Rido httpx status:", r.status_code)
        if r.status_code == 200:
            print("Rido items:", len(r.json().get('data', [])))

asyncio.run(test_rido_httpx())
