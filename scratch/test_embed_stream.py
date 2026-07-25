import requests
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://topxx.vip/"
}

url = "https://embed.streamxx.net/player/tVXgcZsfyy/01fe70572686e43b69b81a46b6fe36e6"
res = requests.get(url, headers=headers)
print("Status:", res.status_code)
print("Content-Type:", res.headers.get("content-type"))

# Search for m3u8 or mp4 or video source links inside html / js
m3u8_links = re.findall(r'https?://[^\s\'"<>]+?\.m3u8[^\s\'"<>]*', res.text)
print("Found M3U8 links:", m3u8_links)

# Print snippet of HTML
print("\nSnippet of HTML:")
print(res.text[:1500])
