import urllib.parse
import json
import re
import base64
import httpx
import asyncio

async def test_nguonc():
    embed_url = 'https://embed18.streamc.xyz/embed.php?hash=c9e5230c3e65847df88fc05ea66cbbb6'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://phim.nguonc.com/'
    }
    
    parsed = urllib.parse.urlparse(embed_url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    print("Domain:", domain)
    
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(embed_url, headers=headers)
        print("Embed Status code:", resp.status_code)
        html = resp.text
        
        obf_match = re.search(r'data-obf="([^"]+)"', html)
        if obf_match:
            obf = obf_match.group(1)
            d1 = json.loads(base64.b64decode(obf).decode('utf-8'))
            sub_str = d1.get('sUb')
            m3u8_url = f"{domain}/{sub_str}?d=1"
            print("Target m3u8 URL:", m3u8_url)
            
            m3u8_resp = await client.get(m3u8_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': embed_url
            })
            print("m3u8 status:", m3u8_resp.status_code)
            print("m3u8 content type:", m3u8_resp.headers.get("content-type"))
            print("m3u8 body sample:\n", m3u8_resp.text[:500])
        else:
            print("data-obf NOT found!")

if __name__ == "__main__":
    asyncio.run(test_nguonc())
