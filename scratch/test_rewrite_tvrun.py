import re
import urllib.parse
from typing import Optional

def rewrite_m3u8_playlist(content: str, base_url: str, referer: Optional[str], proxy_endpoint: str) -> str:
    """Rewrite URLs in m3u8 playlist to route through tvrun stream_proxy."""
    lines = content.splitlines()
    rewritten_lines = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
            
        if stripped.startswith("#"):
            # Check URI= in tags like #EXT-X-KEY, #EXT-X-MEDIA, #EXT-X-MAP
            if 'URI="' in stripped:
                def replace_uri(match):
                    uri = match.group(1)
                    abs_uri = urllib.parse.urljoin(base_url, uri)
                    proxy_uri = f"{proxy_endpoint}?url={urllib.parse.quote(abs_uri, safe='')}"
                    if referer:
                        proxy_uri += f"&referer={urllib.parse.quote(referer, safe='')}"
                    return f'URI="{proxy_uri}"'
                
                new_line = re.sub(r'URI="([^"]+)"', replace_uri, stripped)
                rewritten_lines.append(new_line)
            else:
                rewritten_lines.append(stripped)
        else:
            abs_url = urllib.parse.urljoin(base_url, stripped)
            proxy_url = f"{proxy_endpoint}?url={urllib.parse.quote(abs_url, safe='')}"
            if referer:
                proxy_url += f"&referer={urllib.parse.quote(referer, safe='')}"
            rewritten_lines.append(proxy_url)
            
    return "\n".join(rewritten_lines)

# Test with sample
sample = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:10
#EXT-X-MEDIA-SEQUENCE:0
#EXTINF:10.0,
segment1.ts
#EXTINF:10.0,
https://othercdn.com/segment2.ts
"""
res = rewrite_m3u8_playlist(sample, "https://tv.angiangtv.vn/live/kgtv/kgtv.m3u8", "https://tvrun.online/", "http://127.0.0.1:7860/tvrun/stream_proxy")
print("Rewritten Sample:")
print(res)
