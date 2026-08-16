import urllib.request
import urllib.parse
import json
import re
from bs4 import BeautifulSoup

def main():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://new2.moviesdrive.christmas/'
    }
    url = "https://hubcloud.foo/drive/search-recover.php?from_ac=BLBuI_3M0zIndc8lnxU_oSJJuYQoZ-HIKXkqICte48g_w2A4ajZl&q=RG93bmxvYWQgRGVhZHBvb2wgJiMwMzg7IFdvbHZlcmluZSAyMDI0IDEwODBw"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        print("Final URL:", resp.geturl())
        for line in html.splitlines():
            if 'const Q_INITIAL' in line or 'const FROM_AC_TOKEN' in line:
                print(line)
        
        q_match = re.search(r'const Q_INITIAL\s*=\s*"([^"]+)"', html)
        token_match = re.search(r'const FROM_AC_TOKEN\s*=\s*"([^"]+)"', html)
        if q_match and token_match:
            q_val = q_match.group(1).encode().decode('unicode-escape')
            token_val = token_match.group(1)
            api_url = f"https://hubcloud.cx/drive/search-recover.php?api=search&q={urllib.parse.quote(q_val)}&page=1&from_ac={token_val}"
            req_api = urllib.request.Request(api_url, headers={**headers, 'Referer': resp.geturl(), 'Accept': 'application/json'})
            with urllib.request.urlopen(req_api, timeout=15) as api_resp:
                api_data = json.loads(api_resp.read().decode('utf-8'))
                print("API data:", json.dumps(api_data, indent=2))

if __name__ == '__main__':
    main()
