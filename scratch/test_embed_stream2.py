import requests
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://topxx.vip/"
}

urls = [
    "https://embed.streamxx.net/player/tVXgcZsfyy",
    "https://embed.streamxx.net/player/VMWn8kKjX6"
]

for url in urls:
    res = requests.get(url, headers=headers)
    print(f"URL: {url} -> Status: {res.status_code}")
    if res.status_code == 200:
        m3u8s = re.findall(r'https?://[^\s\'"<>]+?\.m3u8[^\s\'"<>]*', res.text)
        print("m3u8 links:", m3u8s)
        # Search for any player config / hls / video url pattern
        script_sources = re.findall(r'src=["\']([^"\']+)["\']', res.text)
        print("Script sources:", script_sources)
        print("HTML snippet:\n", res.text[:1000])
        print("\n" + "="*50 + "\n")
