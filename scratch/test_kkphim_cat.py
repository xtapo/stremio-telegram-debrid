import urllib.request
import json

url = "https://phimapi.com/danh-sach/phim-moi-cap-nhat?page=1"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    res = urllib.request.urlopen(req)
    data = json.loads(res.read().decode('utf-8'))
    items = data.get('items', [])
    print("Catalog items count:", len(items))
    if items:
        slug = items[0].get('slug')
        print("First film slug:", slug)
        
        detail_url = f"https://phimapi.com/phim/{slug}"
        req2 = urllib.request.Request(detail_url, headers={'User-Agent': 'Mozilla/5.0'})
        res2 = urllib.request.urlopen(req2)
        data2 = json.loads(res2.read().decode('utf-8'))
        episodes = data2.get('episodes', [])
        if episodes:
            s_data = episodes[0].get('server_data', [])
            if s_data:
                print("M3U8 LINK:", s_data[0].get('link_m3u8'))
except Exception as e:
    print("Error:", e)
