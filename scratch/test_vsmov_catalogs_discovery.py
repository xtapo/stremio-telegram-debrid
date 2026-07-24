import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

test_paths = [
    "danh-sach/phim-moi-cap-nhat",
    "danh-sach/phim-le",
    "danh-sach/phim-bo",
    "danh-sach/tv-shows",
    "danh-sach/hoat-hinh",
    "the-loai/hành-động",
    "the-loai/hanh-dong",
    "quoc-gia/trung-quoc",
    "quoc-gia/han-quoc",
    "phim-le",
    "phim-bo",
    "tv-shows",
    "hoat-hinh"
]

headers = {'User-Agent': 'Mozilla/5.0'}

for p in test_paths:
    url = f"https://vsmov.com/api/{p}?page=1"
    try:
        req = urllib.request.Request(url, headers=headers)
        res = urllib.request.urlopen(req, timeout=5)
        text = res.read().decode('utf-8')
        data = json.loads(text)
        items = data.get('items', [])
        print(f"✅ SUCCESS: {url} -> status: {data.get('status')}, count: {len(items)}")
    except Exception as e:
        print(f"❌ FAIL: {url} -> {e}")
