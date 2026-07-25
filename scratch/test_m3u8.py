import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://embed.streamxx.net/"
}

url = "https://embed.streamxx.net/backup-hls/tVXgcZsfyy/main.m3u8"
res = requests.get(url, headers=headers)
print("Status:", res.status_code)
print("Content-Type:", res.headers.get("content-type"))
print("M3U8 text:\n", res.text[:500])
