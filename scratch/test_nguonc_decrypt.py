import urllib.request
import re
import json
import base64
import sys

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

sys.stdout.reconfigure(encoding='utf-8')

embed_url = "https://embed14.streamc.xyz/embed.php?hash=1b8f31744ef1d065cd3aaa250c4eb682"
user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

# Fetch embed HTML
req1 = urllib.request.Request(embed_url, headers={'User-Agent': user_agent, 'Referer': 'https://phim.nguonc.com/'})
html = urllib.request.urlopen(req1).read().decode('utf-8')
obf = re.search(r'data-obf="([^"]+)"', html).group(1)
sub_str = json.loads(base64.b64decode(obf).decode('utf-8'))['sUb']
m3u8_url = f"https://embed14.streamc.xyz/{sub_str}?d=1"

# Fetch encrypted playlist
req2 = urllib.request.Request(m3u8_url, headers={'User-Agent': user_agent, 'Referer': embed_url})
encrypted_m3u8 = urllib.request.urlopen(req2).read().decode('utf-8', errors='ignore')

print("Encrypted M3U8 snippet:\n", encrypted_m3u8[:300])

iv_match = re.search(r'#ENC-AESGCM;iv=([0-9a-fA-F]+)', encrypted_m3u8)
if iv_match:
    iv_hex = iv_match.group(1)
    iv_bytes = bytes.fromhex(iv_hex)
    print("IV bytes length:", len(iv_bytes), "hex:", iv_hex)

# Find the encrypted base64 payload line
lines = [l.strip() for l in encrypted_m3u8.splitlines() if l.strip() and not l.startswith('#')]
if lines:
    payload_b64 = lines[0]
    cipher_bytes = base64.b64decode(payload_b64)
    print("Cipher bytes length:", len(cipher_bytes))
