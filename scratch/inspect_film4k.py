import requests
import json
import re

session_cookie = 'session=eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImphbWlkMjA0QGdtYWlsLmNvbSIsIm5hbWUiOiJUaGkgVHJhbiIsImltYWdlIjoiaHR0cHM6Ly9saDMuZ29vZ2xldXNlcmNvbnRlbnQuY29tL2EvQUNnOG9jSV9HWURzQ3JHaFV4WUN1NVRkNWxka3laRHUxcm5TSUJQVGU0dkJKZUFaalhWYW95aUc9czk2LWMiLCJzdWIiOiI2YTg4NDYyOGQ5MmQwNmI3OTRjNjQ2NzUiLCJpYXQiOjE3ODczMTU3NTIsImV4cCI6MTc4OTkwNzc1Mn0.nNwoSi3H9HwNkYCYVTj4PhS0IVKoAdus4racY3pOMBo'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Cookie': session_cookie
}

with open('scratch/film4k_tv.html', 'r', encoding='utf-8') as f:
    content = f.read()

print("HTML snippet (first 1000 chars):")
print(content[:1000])

# Check for scripts or API calls or embedded data
scripts = re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', content)
print("Scripts:", scripts)

next_data = re.findall(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', content)
if next_data:
    print("Found __NEXT_DATA__")
    data = json.loads(next_data[0])
    with open('scratch/film4k_next_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("pageProps keys:", data.get('props', {}).get('pageProps', {}).keys())
else:
    print("No __NEXT_DATA__, searching for JS bundles or window.__ variables")
    # let's find any inline script
    inline_scripts = re.findall(r'<script(?![^>]*src)[^>]*>(.*?)</script>', content, re.DOTALL)
    print(f"Found {len(inline_scripts)} inline scripts")
    for i, s in enumerate(inline_scripts):
        print(f"--- Inline script {i} (len={len(s)}) ---")
        print(s[:300])
