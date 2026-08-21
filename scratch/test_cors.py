import requests

session_cookie = 'session=eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImphbWlkMjA0QGdtYWlsLmNvbSIsIm5hbWUiOiJUaGkgVHJhbiIsImltYWdlIjoiaHR0cHM6Ly9saDMuZ29vZ2xldXNlcmNvbnRlbnQuY29tL2EvQUNnOG9jSV9HWURzQ3JHaFV4WUN1NVRkNWxka3laRHUxcm5TSUJQVGU0dkJKZUFaalhWYW95aUc9czk2LWMiLCJzdWIiOiI2YTg4NDYyOGQ5MmQwNmI3OTRjNjQ2NzUiLCJpYXQiOjE3ODczMTU3NTIsImV4cCI6MTc4OTkwNzc1Mn0.nNwoSi3H9HwNkYCYVTj4PhS0IVKoAdus4racY3pOMBo'

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Cookie': session_cookie,
    'Referer': 'https://film4k.net/tv'
}

r = requests.get('https://film4k.net/api/tv/vtv1-hd/stream', headers=headers)
data = r.json()
print("Stream data:", data)
stream_url = data.get('url')

# Test fetching master playlist with Origin header (simulate browser fetch)
cors_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Origin': 'http://localhost:7860',
    'Referer': 'http://localhost:7860/'
}
res = requests.get(stream_url, headers=cors_headers)
print("Master playlist status:", res.status_code)
print("Access-Control-Allow-Origin:", res.headers.get('Access-Control-Allow-Origin'))
print("Playlist content sample:\n", res.text[:300])

# Now test child playlist or segment
import urllib.parse
lines = [l.strip() for l in res.text.split('\n') if l.strip() and not l.startswith('#')]
if lines:
    child_url = urllib.parse.urljoin(stream_url, lines[0])
    print("\nChild URL:", child_url)
    res_child = requests.get(child_url, headers=cors_headers)
    print("Child playlist status:", res_child.status_code)
    print("Child Access-Control-Allow-Origin:", res_child.headers.get('Access-Control-Allow-Origin'))
    print("Child playlist sample:\n", res_child.text[:300])
    
    # Test segment
    ts_lines = [l.strip() for l in res_child.text.split('\n') if l.strip() and not l.startswith('#')]
    if ts_lines:
        ts_url = urllib.parse.urljoin(child_url, ts_lines[0])
        print("\nTS URL:", ts_url)
        res_ts = requests.get(ts_url, headers=cors_headers)
        print("TS status:", res_ts.status_code)
        print("TS Access-Control-Allow-Origin:", res_ts.headers.get('Access-Control-Allow-Origin'))
