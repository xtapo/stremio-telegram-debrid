import urllib.request
import re
import json
import gzip

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.vidking.net/',
    'Origin': 'https://www.vidking.net'
}

def fetch(url):
    req = urllib.request.Request(url, headers=headers)
    resp = urllib.request.urlopen(req)
    data = resp.read()
    if resp.info().get('Content-Encoding') == 'gzip':
        data = gzip.decompress(data)
    return data.decode('utf-8', errors='ignore')

def test_embed():
    url = "https://www.vidking.net/embed/movie/550" # Fight Club
    html = fetch(url)
    print("Embed HTML len:", len(html))
    print(html[:1500])
    
    # Check script tags
    scripts = re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', html)
    print("\nScripts in embed:", scripts)
    
    # Check inline scripts
    inline_scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    for i, s in enumerate(inline_scripts):
        if s.strip():
            print(f"\nInline script {i}:", s[:500])

if __name__ == '__main__':
    test_embed()
