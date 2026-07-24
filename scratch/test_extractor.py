import urllib.request
import json
import base64
import re
import sys
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding='utf-8')

def extract_m3u8_from_embed(embed_url: str) -> str:
    try:
        parsed = urlparse(embed_url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        
        req = urllib.request.Request(embed_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://phim.nguonc.com/'
        })
        html = urllib.request.urlopen(req, timeout=5).read().decode('utf-8')
        
        obf_match = re.search(r'data-obf="([^"]+)"', html)
        if obf_match:
            obf = obf_match.group(1)
            d1 = json.loads(base64.b64decode(obf).decode('utf-8'))
            sub_str = d1.get('sUb')
            if sub_str:
                return f"{domain}/{sub_str}?d=1"
    except Exception as e:
        print(f"Extraction error for {embed_url}: {e}")
    return embed_url

# Test 5 embed URLs
urls = [
    "https://embed14.streamc.xyz/embed.php?hash=1b8f31744ef1d065cd3aaa250c4eb682",
    "https://embed15.streamc.xyz/embed.php?hash=77eead9d048d4c8f58993b093b26f3c2",
    "https://embed18.streamc.xyz/embed.php?hash=600756a36f10b7b7302e12288c95653f",
    "https://embed15.streamc.xyz/embed.php?hash=5604dafb94dd89a22e9773fe211c7e9b",
    "https://embed13.streamc.xyz/embed.php?hash=2eec38fc667a153057ef1bb81937218e"
]

for u in urls:
    m3u8 = extract_m3u8_from_embed(u)
    print("Original:", u)
    print("M3U8:    ", m3u8)
    print("-" * 50)
