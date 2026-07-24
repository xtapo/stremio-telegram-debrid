import urllib.parse
import re

def rewrite_m3u8_playlist(m3u8_text: str, base_m3u8_url: str, referer: str, proxy_endpoint_url: str) -> str:
    lines = m3u8_text.splitlines()
    new_lines = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('#'):
            # Check for URI inside #EXT-X-KEY or #EXT-X-MAP
            if 'URI="' in stripped:
                def replace_uri(match):
                    uri = match.group(1)
                    full_uri = urllib.parse.urljoin(base_m3u8_url, uri)
                    proxied = f"{proxy_endpoint_url}?url={urllib.parse.quote(full_uri)}&referer={urllib.parse.quote(referer)}"
                    return f'URI="{proxied}"'
                stripped = re.sub(r'URI="([^"]+)"', replace_uri, stripped)
            new_lines.append(stripped)
        else:
            # Segment URL
            full_segment_url = urllib.parse.urljoin(base_m3u8_url, stripped)
            proxied_segment_url = f"{proxy_endpoint_url}?url={urllib.parse.quote(full_segment_url)}&referer={urllib.parse.quote(referer)}"
            new_lines.append(proxied_segment_url)
            
    return "\n".join(new_lines)

# Test rewrite
sample_m3u8 = """#EXTM3U
#EXT-X-TARGETDURATION:6
#EXTINF:6.0,
segment_0.ts
#EXTINF:6.0,
https://embed18.streamc.xyz/segment_1.ts
"""

res = rewrite_m3u8_playlist(sample_m3u8, "https://embed18.streamc.xyz/playlist.m3u8", "https://embed18.streamc.xyz/embed.php?hash=123", "http://localhost:7071/nguonc/stream_proxy")
print("Rewritten M3U8:\n", res)
