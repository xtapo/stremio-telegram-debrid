import httpx
from bs4 import BeautifulSoup
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}
client = httpx.Client(headers=headers, follow_redirects=True, timeout=15.0)

urls = [
    'https://4khdhub.one/rush-movie-7803/',
    'https://4khdhub.one/outer-banks-series-2214/',
    'https://4khdhub.one/facing-el-chapo-movie-7798/',
]

for url in urls:
    print(f"\n============================\nFetching: {url}")
    r = client.get(url)
    print("Status:", r.status_code)
    soup = BeautifulSoup(r.text, 'html.parser')
    
    title = soup.find('h1')
    print("H1 Title:", title.get_text(strip=True) if title else "None")
    
    # Let's inspect all download links / buttons / tables / forms
    links = soup.find_all('a', href=True)
    download_links = []
    for a in links:
        href = a['href']
        text = a.get_text(strip=True)
        # Check if it's an external link or download link
        if any(kw in href.lower() for kw in ['hubcloud', 'gdflix', 'drive', 'link', 'download', 'fastdl', 'file', 'buzz', 'short', 'token']) or not href.startswith(('https://4khdhub.one', '/', '#')):
            download_links.append((text, href, a.parent.get_text(strip=True)[:100]))
    
    print(f"Found {len(download_links)} candidate download links:")
    for txt, href, parent_txt in download_links:
        print(f"   [{txt}] -> {href} | Context: {parent_txt}")

