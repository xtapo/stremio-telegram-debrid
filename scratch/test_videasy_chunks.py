import httpx
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://player.videasy.to/movie/533535',
}

with httpx.Client(headers=headers, follow_redirects=True, timeout=15) as client:
    r = client.get('https://player.videasy.to/_next/static/chunks/8351-ad3ea010cfe1b6bd.js')
    print("8351 len:", len(r.text))
    # find API calls or domain names
    domains = re.findall(r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', r.text)
    print("Domains:", set(domains))
    
    # find API paths
    paths = re.findall(r'["\'](/api/[^"\']+|/[a-zA-Z0-9_-]+/sources[^"\']*)["\']', r.text)
    print("Paths:", set(paths))
    
    # Also find webpack chunk map
    for m in re.finditer(r'\{[0-9]+:["\'][a-f0-9]+["\']', r.text):
        print("Chunk map snippet:", m.group(0))
