import hmac
import hashlib
import base64
import json
import re
import urllib.parse
import httpx
import asyncio
from typing import Optional, Dict, Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.testclient import TestClient

M3U8_CACHE: Dict[str, Tuple[str, float]] = {}

async def extract_and_decrypt_m3u8(embed_url: str, client: Optional[httpx.AsyncClient] = None) -> str:
    """Extract and decrypt m3u8 playlist from NguonC streamc embed."""
    if not embed_url:
        return ""
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://phim.nguonc.com/'
    }
    
    close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)
        close_client = True
        
    try:
        # 1. Fetch embed page
        resp = await client.get(embed_url, headers=headers)
        if resp.status_code != 200:
            return ""
        html = resp.text
        
        obf_match = re.search(r'data-obf="([^"]+)"', html)
        if not obf_match:
            return ""
            
        obf_data = json.loads(base64.b64decode(obf_match.group(1)).decode('utf-8'))
        sub_str = obf_data.get('sUb')
        video_hash = obf_data.get('hD')
        if not sub_str or not video_hash:
            return ""
            
        parsed = urllib.parse.urlparse(embed_url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        m3u8_endpoint = f"{domain}/{sub_str}?d=1"
        
        # 2. Fetch encrypted m3u8 playlist
        m3u8_resp = await client.get(m3u8_endpoint, headers={
            'User-Agent': headers['User-Agent'],
            'Referer': embed_url
        })
        
        if m3u8_resp.status_code != 200:
            return ""
            
        raw_m3u8_text = m3u8_resp.text
        
        # If plain m3u8 without encryption
        if "#ENC-AESGCM" not in raw_m3u8_text:
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
    except Exception as e:
        print(f"Decryption error for {embed_url}: {e}")
        return ""
    finally:
        if close_client:
            await client.aclose()

def rewrite_m3u8_playlist(m3u8_text: str, base_url: str, referer: str, proxy_endpoint_url: str) -> str:
    lines = m3u8_text.splitlines()
    new_lines = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('#'):
            if 'URI="' in stripped:
                def replace_uri(match):
                    uri = match.group(1)
                    full_uri = urllib.parse.urljoin(base_url, uri)
                    proxied = f"{proxy_endpoint_url}?url={urllib.parse.quote(full_uri, safe='')}&referer={urllib.parse.quote(referer, safe='')}"
                    return f'URI="{proxied}"'
                stripped = re.sub(r'URI="([^"]+)"', replace_uri, stripped)
            new_lines.append(stripped)
        else:
            full_segment_url = urllib.parse.urljoin(base_url, stripped)
            proxied_segment_url = f"{proxy_endpoint_url}?url={urllib.parse.quote(full_segment_url, safe='')}&referer={urllib.parse.quote(referer, safe='')}"
            new_lines.append(proxied_segment_url)
            
    return "\n".join(new_lines)

app = FastAPI()

@app.get("/nguonc/stream_proxy")
async def nguonc_stream_proxy(request: Request, url: Optional[str] = None, embed: Optional[str] = None, referer: Optional[str] = None):
    base_url = str(request.base_url).rstrip("/")
    proxy_endpoint = f"{base_url}/nguonc/stream_proxy"
    
    # Mode 1: embed URL passed directly -> Decrypt and return rewritten m3u8
    if embed:
        ref = referer or embed
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            decrypted_m3u8 = await extract_and_decrypt_m3u8(embed, client)
            if not decrypted_m3u8:
                raise HTTPException(status_code=502, detail="Failed to decrypt NguonC stream")
            rewritten = rewrite_m3u8_playlist(decrypted_m3u8, embed, ref, proxy_endpoint)
            return Response(content=rewritten, media_type="application/vnd.apple.mpegurl")

    if not url:
        raise HTTPException(status_code=400, detail="Missing url or embed parameter")

    if " " in url:
        url = url.replace(" ", "+")

    ref = referer or "https://phim.nguonc.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": ref
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            
            if resp.status_code == 200 and ("#EXTM3U" in resp.text or url.endswith(".m3u8")):
                raw_text = resp.text
                if "#ENC-AESGCM" in raw_text:
                    decrypted = await extract_and_decrypt_m3u8(ref, client)
                    if decrypted:
                        raw_text = decrypted
                rewritten = rewrite_m3u8_playlist(raw_text, url, ref, proxy_endpoint)
                return Response(content=rewritten, status_code=200, media_type="application/vnd.apple.mpegurl")

            return Response(content=resp.content, status_code=resp.status_code, media_type=content_type)
    except Exception as e:
        print("Proxy error:", e)
        raise HTTPException(status_code=500, detail=str(e))

def test_full_pipeline():
    client = TestClient(app)
    embed_url = "https://embed18.streamc.xyz/embed.php?hash=c9e5230c3e65847df88fc05ea66cbbb6"
    
    # 1. Request m3u8 playlist via proxy
    print("Testing /nguonc/stream_proxy with embed...")
    res = client.get(f"/nguonc/stream_proxy?embed={urllib.parse.quote(embed_url, safe='')}")
    print("Playlist Status:", res.status_code)
    print("Playlist Media Type:", res.headers.get("content-type"))
    playlist_text = res.text
    print("Playlist lines count:", len(playlist_text.splitlines()))
    print("Playlist sample:\n", playlist_text[:400])
    
    # 2. Extract first segment URL from playlist
    first_segment_url = None
    for line in playlist_text.splitlines():
        if line.startswith("http://testserver/nguonc/stream_proxy?url="):
            first_segment_url = line.replace("http://testserver", "")
            break
            
    print("\nFirst proxied segment URL:", first_segment_url[:80])
    
    # 3. Request segment through proxy
    seg_res = client.get(first_segment_url)
    print("Segment Status:", seg_res.status_code)
    print("Segment bytes length:", len(seg_res.content))
    print("MPEG-TS Sync Byte (0x47 / 71):", seg_res.content[0] if seg_res.content else None)

if __name__ == "__main__":
    test_full_pipeline()
