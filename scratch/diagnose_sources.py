import httpx
import requests
import re

print("=== 1. Testing Rido with full headers ===")
rido_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://ridomovies.su/",
    "Origin": "https://ridomovies.su",
    "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin"
}
r_rido = requests.get("https://ridomovies.su/api/search?q=avatar", headers=rido_headers)
print("Rido requests status:", r_rido.status_code, "json len:", len(r_rido.json().get('data', [])) if r_rido.status_code == 200 else r_rido.text[:100])

print("\n=== 2. Testing CLB without _embed ===")
clb_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://clbphimxua.com/"
}
r_clb = requests.get("https://clbphimxua.com/wp-json/wp/v2/posts", headers=clb_headers)
print("CLB posts status:", r_clb.status_code, r_clb.text[:200])

print("\n=== 3. Inspecting Yanhh HTML ===")
r_yanhh = requests.get("https://yanhh3d.run/hoat-hinh-4k?page=1", headers=clb_headers)
print("Yanhh status:", r_yanhh.status_code, "len:", len(r_yanhh.text))
with open("scratch/yanhh_sample.html", "w", encoding="utf-8") as f:
    f.write(r_yanhh.text)

# Find cards pattern in yanhh
matches = re.findall(r'<div class="item[^"]*">([\s\S]*?)</div>\s*</div>', r_yanhh.text)
if not matches:
    matches = re.findall(r'<a\s+href="([^"]+)"[^>]*>([\s\S]*?)</a>', r_yanhh.text)
print("Yanhh found matches:", len(matches))
for m in matches[:5]:
    print("  sample:", m)
