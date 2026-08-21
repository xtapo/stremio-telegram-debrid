import requests
import json

session_cookie = 'session=eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImphbWlkMjA0QGdtYWlsLmNvbSIsIm5hbWUiOiJUaGkgVHJhbiIsImltYWdlIjoiaHR0cHM6Ly9saDMuZ29vZ2xldXNlcmNvbnRlbnQuY29tL2EvQUNnOG9jSV9HWURzQ3JHaFV4WUN1NVRkNWxka3laRHUxcm5TSUJQVGU0dkJKZUFaalhWYW95aUc9czk2LWMiLCJzdWIiOiI2YTg4NDYyOGQ5MmQwNmI3OTRjNjQ2NzUiLCJpYXQiOjE3ODczMTU3NTIsImV4cCI6MTc4OTkwNzc1Mn0.nNwoSi3H9HwNkYCYVTj4PhS0IVKoAdus4racY3pOMBo'

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Cookie': session_cookie,
    'Referer': 'https://film4k.net/tv'
}

r = requests.get('https://film4k.net/api/tv/vtv3-hd/stream', headers=headers)
data = r.json()
print("VTV3 Stream URL:", data.get('url'))

# Test fetching the m3u8 playlist directly WITHOUT cookies or referer (e.g. from standard video player)
m3u8_url = data.get('url')
if m3u8_url:
    res = requests.get(m3u8_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
    print("M3U8 fetch status:", res.status_code)
    print("M3U8 first 300 chars:")
    print(res.text[:300])
