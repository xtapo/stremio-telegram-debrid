import urllib.request

seg_url = "https://p25.streamvsmov.com/file/ZnVja3lvdWZ1Y2t5b3U/tiktok/7fdbf8da-4b58-46ff-a2db-b1f449d4b8f8/file-tiktok_1.png"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://v13.streamvsmov.com/'
}

req = urllib.request.Request(seg_url, headers=headers)
res = urllib.request.urlopen(req, timeout=5)
raw_content = res.read()

def strip_fake_png_header(content: bytes) -> bytes:
    if not content.startswith(b"\x89PNG"):
        return content
    pos = 0
    while True:
        pos = content.find(b'G', pos)
        if pos == -1 or pos > 2048:
            break
        if pos + 188 < len(content) and content[pos + 188] == 0x47:
            if pos + 376 < len(content) and content[pos + 376] == 0x47:
                return content[pos:]
        pos += 1
    return content

clean_ts = strip_fake_png_header(raw_content)

print("Raw content length:", len(raw_content))
print("Clean TS content length:", len(clean_ts))
print("Header byte:", clean_ts[0], "(Expected 71 for 'G')")
print("Byte 188:", clean_ts[188], "(Expected 71 for 'G')")
print("Byte 376:", clean_ts[376], "(Expected 71 for 'G')")

assert clean_ts[0] == 0x47
assert clean_ts[188] == 0x47
assert clean_ts[376] == 0x47
print("\n🎉 FAKE PNG HEADER STRIPPED PERFECTLY! 100% VALID TS VIDEO SEGMENT!")
