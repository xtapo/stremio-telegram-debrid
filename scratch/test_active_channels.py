import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

session_cookie = 'session=eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImphbWlkMjA0QGdtYWlsLmNvbSIsIm5hbWUiOiJUaGkgVHJhbiIsImltYWdlIjoiaHR0cHM6Ly9saDMuZ29vZ2xldXNlcmNvbnRlbnQuY29tL2EvQUNnOG9jSV9HWURzQ3JHaFV4WUN1NVRkNWxka3laRHUxcm5TSUJQVGU0dkJKZUFaalhWYW95aUc9czk2LWMiLCJzdWIiOiI2YTg4NDYyOGQ5MmQwNmI3OTRjNjQ2NzUiLCJpYXQiOjE3ODczMTU3NTIsImV4cCI6MTc4OTkwNzc1Mn0.nNwoSi3H9HwNkYCYVTj4PhS0IVKoAdus4racY3pOMBo'

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Cookie': session_cookie,
    'Referer': 'https://film4k.net/tv'
}

with open('scratch/film4k_channels.json', 'r', encoding='utf-8') as f:
    channels = json.load(f).get('channels', [])

print(f"Total channels in list: {len(channels)}")

active = 0
failed = 0
results = {}

for ch in channels[:40]:
    ch_id = ch['id']
    name = ch.get('name', '')
    try:
        r = requests.get(f'https://film4k.net/api/tv/{ch_id}/stream', headers=headers, timeout=5)
        if r.status_code == 200 and r.json().get('url'):
            active += 1
            results[ch_id] = {'status': 200, 'name': name, 'url': r.json().get('url')}
        else:
            failed += 1
            results[ch_id] = {'status': r.status_code, 'name': name}
    except Exception as e:
        failed += 1
        results[ch_id] = {'status': 'error', 'error': str(e)}

print(f"Tested 40 channels: {active} Active (200 OK), {failed} Inactive/502")
for ch_id, res in list(results.items())[:15]:
    status_icon = "✅" if res['status'] == 200 else "❌"
    print(f" {status_icon} {res['name']:25} -> {res['status']}")
