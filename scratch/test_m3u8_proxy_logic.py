import urllib.request
import urllib.parse
import re
import json
import base64
import sys

sys.stdout.reconfigure(encoding='utf-8')

embed_url = "https://embed14.streamc.xyz/embed.php?hash=1b8f31744ef1d065cd3aaa250c4eb682"
user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

req1 = urllib.request.Request(embed_url, headers={'User-Agent': user_agent, 'Referer': 'https://phim.nguonc.com/'})
html = urllib.request.urlopen(req1).read().decode('utf-8')
obf = re.search(r'data-obf="([^"]+)"', html).group(1)
sub_str = json.loads(base64.b64decode(obf).decode('utf-8'))['sUb']
m3u8_url = f"https://embed14.streamc.xyz/{sub_str}?d=1"

# Fetch playlist
req2 = urllib.request.Request(m3u8_url, headers={'User-Agent': user_agent, 'Referer': embed_url})
playlist_text = urllib.request.urlopen(req2).read().decode('utf-8', errors='ignore')

print("Playlist lines count:", len(playlist_text.splitlines()))
for line in playlist_text.splitlines()[:15]:
    print("  ", line)

# Check segment lines
lines = [line.strip() for line in playlist_text.splitlines() if line.strip() and not line.startswith('#')]
if lines:
    first_seg = lines[0]
    full_seg_url = urllib.parse.urljoin(m3u8_url, first_seg)
    print("\nFirst segment full URL:", full_seg_url)
    
    # Test segment fetch
    try:
        req_seg = urllib.request.Request(full_seg_url, headers={'User-Agent': user_agent, 'Referer': embed_url})
        res_seg = urllib.request.urlopen(req_seg)
        print("Segment Fetch Status:", res_seg.status, "Content-Type:", res_seg.headers.get('Content-Type'), "Size:", len(res_seg.read()))
    except Exception as e:
        print("Segment Fetch Error:", e)
