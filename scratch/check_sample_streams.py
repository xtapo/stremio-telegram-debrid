import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

session_cookie = 'session=eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImphbWlkMjA0QGdtYWlsLmNvbSIsIm5hbWUiOiJUaGkgVHJhbiIsImltYWdlIjoiaHR0cHM6Ly9saDMuZ29vZ2xldXNlcmNvbnRlbnQuY29tL2EvQUNnOG9jSV9HWURzQ3JHaFV4WUN1NVRkNWxka3laRHUxcm5TSUJQVGU0dkJKZUFaalhWYW95aUc9czk2LWMiLCJzdWIiOiI2YTg4NDYyOGQ5MmQwNmI3OTRjNjQ2NzUiLCJpYXQiOjE3ODczMTU3NTIsImV4cCI6MTc4OTkwNzc1Mn0.nNwoSi3H9HwNkYCYVTj4PhS0IVKoAdus4racY3pOMBo'

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Cookie': session_cookie,
    'Referer': 'https://film4k.net/tv'
}

with open('scratch/film4k_channels.json', 'r', encoding='utf-8') as f:
    channels = json.load(f).get('channels', [])

print(f"Total channels: {len(channels)}")

# Let's test streams for sample channels
sample_channels = channels[:15]
results = []
for ch in sample_channels:
    ch_id = ch['id']
    name = ch.get('name', '')
    try:
        r = requests.get(f'https://film4k.net/api/tv/{ch_id}/stream', headers=headers, timeout=10)
        status = r.status_code
        data = r.json() if r.ok else {}
        print(f"Channel: {ch_id:25} ({name:20}) -> status={status}, keys={list(data.keys())}")
        if data.get('url'):
            print(f"   URL: {data['url']}")
        results.append({'id': ch_id, 'name': name, 'status': status, 'data': data})
    except Exception as e:
        print(f"Channel: {ch_id:25} -> Error: {e}")

with open('scratch/sample_stream_results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
