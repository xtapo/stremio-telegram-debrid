import urllib.request
import urllib.parse
import re
import json
import base64
import sys

sys.stdout.reconfigure(encoding='utf-8')

# 1. Fetch embed page
embed_url = "https://embed14.streamc.xyz/embed.php?hash=1b8f31744ef1d065cd3aaa250c4eb682"
req = urllib.request.Request(embed_url, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Referer': 'https://phim.nguonc.com/'
})
html = urllib.request.urlopen(req).read().decode('utf-8')
obf = re.search(r'data-obf="([^"]+)"', html).group(1)
d1 = json.loads(base64.b64decode(obf).decode('utf-8'))
sub_str = d1['sUb']
m3u8_url = f"https://embed14.streamc.xyz/{sub_str}?d=1"

print("M3U8 URL:", m3u8_url)

# Test 1: Fetching M3U8 with NO headers (like default ExoPlayer / Stremio player)
try:
    req_no_header = urllib.request.Request(m3u8_url)
    res = urllib.request.urlopen(req_no_header)
    print("Test 1 (No headers): Status", res.status, "Length:", len(res.read()))
except Exception as e:
    print("Test 1 (No headers): Failed with", e)

# Test 2: Fetching M3U8 WITH Referer header
try:
    req_ref = urllib.request.Request(m3u8_url, headers={'Referer': 'https://embed14.streamc.xyz/'})
    res = urllib.request.urlopen(req_ref)
    m3u8_content = res.read().decode('utf-8', errors='ignore')
    print("Test 2 (With Referer): Status", res.status)
    print("First 300 chars of m3u8:\n", m3u8_content[:300])
    
    # Extract segment URLs inside M3U8 playlist
    lines = [line.strip() for line in m3u8_content.splitlines() if line.strip() and not line.startswith('#')]
    if lines:
        seg_url = lines[0]
        if not seg_url.startswith('http'):
            seg_url = urllib.parse.urljoin(m3u8_url, seg_url)
        print("\nSegment 0 URL:", seg_url)
        
        # Test fetching segment without Referer vs with Referer
        try:
            r_seg1 = urllib.request.urlopen(urllib.request.Request(seg_url))
            print("Segment fetch without Referer: OK, size", len(r_seg1.read()))
        except Exception as e:
            print("Segment fetch without Referer: FAILED with", e)
            
        try:
            r_seg2 = urllib.request.urlopen(urllib.request.Request(seg_url, headers={'Referer': 'https://embed14.streamc.xyz/'}))
            print("Segment fetch with Referer: OK, size", len(r_seg2.read()))
        except Exception as e:
            print("Segment fetch with Referer: FAILED with", e)
            
except Exception as e:
    print("Test 2 (With Referer): Failed with", e)
