import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

slug = "duong-ba-ho-diem-thu-huong-17848938329438"
url = f"https://vsmov.com/api/phim/{slug}"

headers = {'User-Agent': 'Mozilla/5.0'}

try:
    req = urllib.request.Request(url, headers=headers)
    res = urllib.request.urlopen(req, timeout=5)
    data = json.loads(res.read().decode('utf-8'))
    episodes = data.get('episodes', [])
    print("Episodes len:", len(episodes))
    print("Episodes raw:", episodes)
except Exception as e:
    print("Error fetching film detail:", e)
