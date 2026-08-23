import httpx
import re

with httpx.Client(headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36', 'Referer': 'https://gn1r5n.org/e/3z1zvkcqen2d'}, follow_redirects=True, timeout=15) as client:
    r = client.get('https://gn1r5n.org/assets/index-DocunfmE.js')
    text = r.text
    # Search for all strings passed into Gv
    for m in re.finditer(r'Gv\(\s*["\']([^"\']+)["\']', text):
        print("Gv literal:", m.group(1))
    
    # Check if there are other files in gn1r5n or index.html
    r_html = client.get('https://gn1r5n.org/e/3z1zvkcqen2d')
    print("HTML script tags:", re.findall(r'<script[^>]*src="([^"]+)"', r_html.text))
    # Also find any inline window variables
    print("HTML window vars:", re.findall(r'window\.[a-zA-Z0-9_]+\s*=', r_html.text))
