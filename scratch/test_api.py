import requests
import json

session_cookie = 'session=eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImphbWlkMjA0QGdtYWlsLmNvbSIsIm5hbWUiOiJUaGkgVHJhbiIsImltYWdlIjoiaHR0cHM6Ly9saDMuZ29vZ2xldXNlcmNvbnRlbnQuY29tL2EvQUNnOG9jSV9HWURzQ3JHaFV4WUN1NVRkNWxka3laRHUxcm5TSUJQVGU0dkJKZUFaalhWYW95aUc9czk2LWMiLCJzdWIiOiI2YTg4NDYyOGQ5MmQwNmI3OTRjNjQ2NzUiLCJpYXQiOjE3ODczMTU3NTIsImV4cCI6MTc4OTkwNzc1Mn0.nNwoSi3H9HwNkYCYVTj4PhS0IVKoAdus4racY3pOMBo'

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Cookie': session_cookie,
    'Referer': 'https://film4k.net/tv'
}

print("1. Testing /api/auth/me...")
r = requests.get('https://film4k.net/api/auth/me', headers=headers)
print("Auth status:", r.status_code)
try:
    print("Auth data:", json.dumps(r.json(), indent=2, ensure_ascii=False))
except:
    print(r.text)

print("\n2. Testing /api/tv/channels...")
r = requests.get('https://film4k.net/api/tv/channels', headers=headers)
print("Channels status:", r.status_code)
channels_data = None
try:
    channels_data = r.json()
    with open('scratch/film4k_channels.json', 'w', encoding='utf-8') as f:
        json.dump(channels_data, f, indent=2, ensure_ascii=False)
    print(f"Got {len(channels_data.get('channels', []))} channels!")
    for ch in channels_data.get('channels', [])[:5]:
        print(" -", ch)
except Exception as e:
    print("Error parsing channels:", e, r.text)

print("\n3. Testing /api/tv/events...")
r = requests.get('https://film4k.net/api/tv/events', headers=headers)
print("Events status:", r.status_code)
try:
    events_data = r.json()
    with open('scratch/film4k_events.json', 'w', encoding='utf-8') as f:
        json.dump(events_data, f, indent=2, ensure_ascii=False)
    print(f"Got {len(events_data.get('events', []))} events!")
    for ev in events_data.get('events', [])[:5]:
        print(" -", ev)
except Exception as e:
    print("Error parsing events:", e, r.text)

if channels_data and channels_data.get('channels'):
    ch0 = channels_data['channels'][0]
    ch0_id = ch0['id']
    print(f"\n4. Testing /api/tv/{ch0_id}/stream...")
    r = requests.get(f'https://film4k.net/api/tv/{ch0_id}/stream', headers=headers)
    print("Stream status:", r.status_code)
    try:
        print("Stream data:", json.dumps(r.json(), indent=2, ensure_ascii=False))
    except:
        print(r.text)
