import urllib.request
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

url = "https://v13.streamvsmov.com/video/7fdbf8da-4b58-46ff-a2db-b1f449d4b8f8"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://vsmov.com/'})

try:
    res = urllib.request.urlopen(req, timeout=5)
    html = res.read().decode('utf-8')
    
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    for i, s in enumerate(scripts):
        if 'player' in s.lower() or 'subtitles' in s.lower() or 'm3u8' in s.lower() or 'url' in s.lower():
            print(f"=== Script #{i+1} ===")
            print(s)
except Exception as e:
    print("Error:", e)
