import base64
import re
import httpx

def test_extract_domain():
    url = "https://moviesdrives.cfd/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    resp = httpx.get(url, headers=headers, follow_redirects=True, timeout=10.0)
    print("Status:", resp.status_code)
    html = resp.text
    
    # 1. Regex find atob calls: atob(['"](...)['"])
    found_urls = set()
    for m in re.finditer(r'atob\(["\']([A-Za-z0-9+/=]+)["\']\)', html):
        b64 = m.group(1)
        try:
            decoded = base64.b64decode(b64).decode('utf-8', errors='ignore')
            # Extract URLs from decoded
            for u in re.findall(r'https?://[a-zA-Z0-9.-]+(?:/[a-zA-Z0-9._/-]*)?', decoded):
                if "moviesdrive" in u.lower() or "mdrive" in u.lower():
                    found_urls.add(u.rstrip('/'))
        except Exception:
            pass
            
    # 2. Also search for any general base64 strings in script tags
    for script in re.findall(r'<script[^>]*>(.*?)</script>', html, flags=re.DOTALL):
        for b64 in re.findall(r'["\']([A-Za-z0-9+/=]{16,})["\']', script):
            try:
                decoded = base64.b64decode(b64).decode('utf-8', errors='ignore')
                for u in re.findall(r'https?://[a-zA-Z0-9.-]+(?:/[a-zA-Z0-9._/-]*)?', decoded):
                    if "moviesdrive" in u.lower() or "mdrive" in u.lower():
                        found_urls.add(u.rstrip('/'))
            except Exception:
                pass
                
    # 3. Also regex in raw html for direct urls/links
    for u in re.findall(r'https?://[a-zA-Z0-9.-]*moviesdrive[a-zA-Z0-9.-]*', html, flags=re.IGNORECASE):
        found_urls.add(u.rstrip('/'))

    print("Found domain candidates:", found_urls)

if __name__ == "__main__":
    test_extract_domain()
