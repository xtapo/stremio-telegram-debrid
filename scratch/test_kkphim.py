import urllib.request
import json
import sys

url = "https://phimapi.com/phim/nguoi-ban-tuyet-voi"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    res = urllib.request.urlopen(req)
    data = json.loads(res.read().decode('utf-8'))
    print("KKPhim Status:", data.get('status'))
    episodes = data.get('episodes', [])
    if episodes:
        print("First server:", episodes[0].get('server_name'))
        items = episodes[0].get('server_data', [])
        if items:
            print("First ep name:", items[0].get('name'))
            print("First ep m3u8 link:", items[0].get('link_m3u8'))
except Exception as e:
    print("Error:", e)
