import urllib.request
import sys

sys.stdout.reconfigure(encoding='utf-8')

seg_url = "https://p25.streamvsmov.com/file/ZnVja3lvdWZ1Y2t5b3U/tiktok/7fdbf8da-4b58-46ff-a2db-b1f449d4b8f8/file-tiktok_1.png"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://v13.streamvsmov.com/'
}

try:
    req = urllib.request.Request(seg_url, headers=headers)
    res = urllib.request.urlopen(req, timeout=5)
    content = res.read()
    
    print("Content length:", len(content))
    print("First 128 bytes (hex):\n", content[:128].hex())
    
    # Search for TS sync byte 0x47
    pos = content.find(b'G', 8)
    print("First 'G' (0x47) pos after PNG header:", pos)
    
    # Check if 0x47 repeats every 188 bytes
    if pos != -1:
        is_ts = True
        for i in range(1, 10):
            if pos + (i * 188) >= len(content) or content[pos + (i * 188)] != 0x47:
                is_ts = False
                break
        print(f"Is valid MPEG-TS starting at byte offset {pos}? -> {is_ts}")
except Exception as e:
    print("Error:", e)
