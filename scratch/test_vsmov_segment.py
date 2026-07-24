import urllib.request
import sys

sys.stdout.reconfigure(encoding='utf-8')

seg_url = "https://p25.streamvsmov.com/file/ZnVja3lvdWZ1Y2t5b3U/tiktok/7fdbf8da-4b58-46ff-a2db-b1f449d4b8f8/file-tiktok_1.png"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://v13.streamvsmov.com/'
}

try:
    req = urllib.request.Request(seg_url, headers=headers)
    res = urllib.request.urlopen(req, timeout=5)
    content = res.read()
    print(f"Segment fetch status: {res.status}, length: {len(content)}")
    print("Response headers:")
    for k, v in res.headers.items():
        print(f"  {k}: {v}")
    print("First 16 bytes:", content[:16])
except Exception as e:
    print("Error fetching segment:", e)
