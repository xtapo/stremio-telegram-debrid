import urllib.request
import re

url = 'https://embed.streamc.xyz/embed.php?hash=30fa9e72a99c1cb3dabdf8a2e4222061'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(req).read().decode('utf-8')

scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
for i, s in enumerate(scripts):
    print(f"=== Script {i} ===")
    print(s.strip())
