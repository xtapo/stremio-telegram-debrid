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

# Test a few channels
channels = ['vtv1-hd', 'vtv3-hd', 'vtv6-hd', 'htv7-hd', 'k-plus-sport-1-hd', 'k-plus-cine-hd', 'hbo-hd', 'cinemax-hd']

for ch_id in channels:
    r = requests.get(f'https://film4k.net/api/tv/{ch_id}/stream', headers=headers)
    print(f"Channel {ch_id}: status={r.status_code}")
    if r.ok:
        try:
            data = r.json()
            print(" ->", json.dumps(data, indent=2, ensure_ascii=False))
            # Test stream url
            if 'url' in data:
                head_res = requests.head(data['url'], headers={'User-Agent': headers['User-Agent']}, timeout=5)
                print(f" -> stream HEAD status: {head_res.status_code}")
        except Exception as e:
            print(" -> error:", e, r.text[:200])
    else:
        print(" -> failed:", r.status_code, r.text)

# Also test a live event
with open('scratch/film4k_events.json', 'r', encoding='utf-8') as f:
    events = json.load(f).get('events', [])

print(f"\nTotal events: {len(events)}")
for ev in events[:3]:
    ev_id = ev['id']
    title = ev.get('title', '')
    print(f"\nEvent {ev_id} ({title}):")
    r = requests.get(f'https://film4k.net/api/tv/{ev_id}/stream', headers=headers)
    print(f"Event stream status: {r.status_code}")
    if r.ok:
        print(" ->", json.dumps(r.json(), indent=2, ensure_ascii=False))
