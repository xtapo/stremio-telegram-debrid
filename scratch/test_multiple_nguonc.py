import sys
sys.stdout.reconfigure(encoding='utf-8')

import hmac
import hashlib
import base64
import json
import re
import urllib.parse
import httpx
import asyncio
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

async def extract_and_decrypt_m3u8(embed_url: str, client: httpx.AsyncClient) -> str:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://phim.nguonc.com/'
    }
    # 1. Fetch embed page
    resp = await client.get(embed_url, headers=headers)
    html = resp.text
    
    obf_match = re.search(r'data-obf="([^"]+)"', html)
    if not obf_match:
        return ""
    
    obf_data = json.loads(base64.b64decode(obf_match.group(1)).decode('utf-8'))
    sub_str = obf_data.get('sUb')
    video_hash = obf_data.get('hD')
    
    parsed = urllib.parse.urlparse(embed_url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    m3u8_url = f"{domain}/{sub_str}?d=1"
    
    # 2. Fetch encrypted m3u8 playlist
    m3u8_resp = await client.get(m3u8_url, headers={
        'User-Agent': headers['User-Agent'],
        'Referer': embed_url
    })
    
    raw_m3u8_text = m3u8_resp.text
    if "#ENC-AESGCM" not in raw_m3u8_text:
        # If plain m3u8 already
        if "#EXTM3U" in raw_m3u8_text:
            return raw_m3u8_text
        return ""

    # 3. Parse IV and base64 body
    iv_match = re.search(r'#ENC-AESGCM;iv=([0-9a-fA-F]+)', raw_m3u8_text)
    if not iv_match:
        return ""
    
    iv_hex = iv_match.group(1)
    iv_bytes = bytes.fromhex(iv_hex)
    
    b64_lines = [line.strip() for line in raw_m3u8_text.splitlines() if line.strip() and not line.strip().startswith('#')]
    b64_str = "".join(b64_lines)
    encrypted_bytes = base64.b64decode(b64_str)
    
    # 4. Derive AES key using HMAC-SHA256
    hmac_key = b"stream-derive-v1"
    derived_aes_key = hmac.new(hmac_key, video_hash.encode('utf-8'), hashlib.sha256).digest()
    
    # 5. Decrypt using AES-GCM
    aesgcm = AESGCM(derived_aes_key)
    decrypted_bytes = aesgcm.decrypt(iv_bytes, encrypted_bytes, None)
    return decrypted_bytes.decode('utf-8')

async def test_multiple_films():
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        # Fetch 5 movies from NguonC
        cat_resp = await client.get('https://phim.nguonc.com/api/films/phim-moi-cap-nhat?page=1')
        items = cat_resp.json().get('items', [])[:5]
        
        for item in items:
            slug = item['slug']
            name = item['name']
            detail_resp = await client.get(f'https://phim.nguonc.com/api/film/{slug}')
            movie = detail_resp.json().get('movie', {})
            episodes = movie.get('episodes', [])
            
            print(f"\nFilm: {slug} - {name}")
            for s in episodes:
                s_name = s.get('server_name')
                first_ep = s.get('items', [])[0] if s.get('items') else None
                if first_ep and first_ep.get('embed'):
                    embed = first_ep['embed']
                    try:
                        m3u8 = await extract_and_decrypt_m3u8(embed, client)
                        is_valid = "#EXTM3U" in m3u8
                        print(f"  [{s_name}] embed: {embed} -> Decrypted: {'SUCCESS' if is_valid else 'FAIL'} (len: {len(m3u8)})")
                    except Exception as e:
                        print(f"  [{s_name}] embed: {embed} -> ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_multiple_films())
