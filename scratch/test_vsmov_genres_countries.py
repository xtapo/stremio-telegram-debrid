import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {'User-Agent': 'Mozilla/5.0'}

genres_url = "https://vsmov.com/api/the-loai"
countries_url = "https://vsmov.com/api/quoc-gia"

try:
    res = urllib.request.urlopen(urllib.request.Request(genres_url, headers=headers))
    data = json.loads(res.read().decode('utf-8'))
    print("Genres:", data)
except Exception as e:
    print("Error genres:", e)

try:
    res = urllib.request.urlopen(urllib.request.Request(countries_url, headers=headers))
    data = json.loads(res.read().decode('utf-8'))
    print("Countries:", data)
except Exception as e:
    print("Error countries:", e)
