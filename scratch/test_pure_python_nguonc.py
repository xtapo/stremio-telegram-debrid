import hmac
import hashlib
import base64
import json
import re
import urllib.parse
import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

async def test_pure_python_decrypt():
    embed_url = 'https://embed18.streamc.xyz/embed.php?hash=c9e5230c3e65847df88fc05ea66cbbb6'
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://phim.nguonc.com/'
    }
    
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        # 1. Fetch embed page
        resp = await client.get(embed_url, headers=headers)
        html = resp.text
        
        obf_match = re.search(r'data-obf="([^"]+)"', html)
        if not obf_match:
            print("data-obf not found")
            return
        
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
        
        # 3. Parse IV and base64 body
        iv_match = re.search(r'#ENC-AESGCM;iv=([0-9a-fA-F]+)', raw_m3u8_text)
        if not iv_match:
            print("IV not found in raw m3u8")
            return
        
        iv_hex = iv_match.group(1)
        iv_bytes = bytes.fromhex(iv_hex)
        
        # Filter lines to get base64 body
        b64_lines = []
        for line in raw_m3u8_text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            b64_lines.append(line)
            
        b64_str = "".join(b64_lines)
        encrypted_bytes = base64.b64decode(b64_str)
        
        # 4. Derive AES key using HMAC-SHA256
        # Key: "stream-derive-v1", Data: video_hash
        hmac_key = b"stream-derive-v1"
        derived_aes_key = hmac.new(hmac_key, video_hash.encode('utf-8'), hashlib.sha256).digest()
        
        # 5. Decrypt using AES-GCM
        aesgcm = AESGCM(derived_aes_key)
        decrypted_bytes = aesgcm.decrypt(iv_bytes, encrypted_bytes, None)
        decrypted_m3u8 = decrypted_bytes.decode('utf-8')
        
        print("\n" + "="*50)
        print("SUCCESS! Decrypted M3U8 length:", len(decrypted_m3u8))
        print("Sample playlist:\n", decrypted_m3u8[:600])
        print("="*50)

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_pure_python_decrypt())
