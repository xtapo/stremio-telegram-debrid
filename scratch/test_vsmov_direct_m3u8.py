import urllib.request
import sys

sys.stdout.reconfigure(encoding='utf-8')

m3u8_url = "https://v13.streamvsmov.com/stream/7fdbf8da-4b58-46ff-a2db-b1f449d4b8f8/master.m3u8"
embed_url = "https://v13.streamvsmov.com/video/7fdbf8da-4b58-46ff-a2db-b1f449d4b8f8"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': embed_url
}

try:
    req = urllib.request.Request(m3u8_url, headers=headers)
    res = urllib.request.urlopen(req, timeout=5)
    text = res.read().decode('utf-8')
    print(f"🎉 M3U8 FETCH SUCCESS! Status {res.status}, length {len(text)}")
    print("=== M3U8 CONTENT PREVIEW ===")
    print(text[:600])
except Exception as e:
    print("Error fetching m3u8:", e)
