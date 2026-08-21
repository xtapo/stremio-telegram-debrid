import requests
import json

session_cookie = 'session=eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImphbWlkMjA0QGdtYWlsLmNvbSIsIm5hbWUiOiJUaGkgVHJhbiIsImltYWdlIjoiaHR0cHM6Ly9saDMuZ29vZ2xldXNlcmNvbnRlbnQuY29tL2EvQUNnOG9jSV9HWURzQ3JHaFV4WUN1NVRkNWxka3laRHUxcm5TSUJQVGU0dkJKZUFaalhWYW95aUc9czk2LWMiLCJzdWIiOiI2YTg4NDYyOGQ5MmQwNmI3OTRjNjQ2NzUiLCJpYXQiOjE3ODczMTU3NTIsImV4cCI6MTc4OTkwNzc1Mn0.nNwoSi3H9HwNkYCYVTj4PhS0IVKoAdus4racY3pOMBo'

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Cookie': session_cookie,
    'Referer': 'https://film4k.net/tv'
}

channels_test = ['vtv1-hd', 'vtv3-hd', 'k-plus-sport-1-hd', 'k-plus-cine-hd', 'hbo-hd', 'htv7-hd', 'thvl1']

for ch in channels_test:
    r = requests.get(f'https://film4k.net/api/tv/{ch}/stream', headers=headers)
    print(f"Channel {ch:20}: status={r.status_code}")
    if r.ok:
        data = r.json()
        print("   Response keys:", list(data.keys()))
        print("   URL:", data.get('url'))
        if 'clearKeys' in data or 'clearKey' in data or 'licenseUrl' in data:
            print("   DRM:", {k: data[k] for k in ['clearKeys', 'clearKey', 'licenseUrl'] if k in data})
