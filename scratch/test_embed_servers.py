import httpx
from bs4 import BeautifulSoup
import re
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://movies2watch.vc/'
}

urls = [
    ("UpCloud", "https://0123movie.space/mv/tt15398776/872585/"),
    ("Vidmoly", "https://0123movie.space/vmf/tt15398776/872585/"),
    ("Videasy", "https://player.videasy.net/movie/872585"),
    ("Vidsrc", "https://vidsrc.cc/v2/embed/movie/tt15398776"),
    ("Vidfast", "https://vidfast.pro/movie/tt15398776"),
]

with httpx.Client(headers=headers, follow_redirects=True, timeout=15) as client:
    for name, url in urls:
        try:
            r = client.get(url, headers={'Referer': 'https://movies2watch.vc/'})
            print(f"\n=== {name} ({url}) ===")
            print(f"Status: {r.status_code}, Final URL: {r.url}")
            soup = BeautifulSoup(r.text, 'html.parser')
            iframes = soup.select('iframe')
            scripts = soup.select('script')
            print(f"iframes: {[i.get('src') for i in iframes]}")
            # check for m3u8 or player sources in scripts
            m3u8s = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', r.text)
            print(f"m3u8s found: {m3u8s}")
            for s in scripts:
                if s.get('src'):
                    print(" script src:", s.get('src'))
                elif any(k in s.text for k in ['file', 'source', 'hls', 'player', 'eval', 'jwplayer', 'vidsrc', 'videasy']):
                    print(" script snippet:", s.text[:200].replace('\n', ' '))
        except Exception as e:
            print(f"Error for {name}: {e}")
