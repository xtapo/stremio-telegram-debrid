import httpx
from bs4 import BeautifulSoup
import re

client = httpx.Client(headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}, follow_redirects=True, timeout=20)

def inspect_urls():
    test_urls = [
        'https://uhdmovies.autos/download-avatar-the-way-of-water-2022-dual-audio-hindi-english-2160p-4k-1080p-x264-hevc-hdr-dovi-web-dl-esubs/',
        'https://uhdmovies.autos/download-interstellar-2014-imax-dual-audio-hindi-english-4k-2160p-1080p-720p-bluray-esub/',
        'https://uhdmovies.autos/download-oppenheimer-2023-dual-audio-hindi-english-2160p-4k-1080p-720p-bluray-esubs/',
        'https://uhdmovies.autos/download-deadpool-wolverine-2024-dual-audio-hindi-english-2160p-4k-1080p-720p-web-dl-esubs/',
        'https://uhdmovies.autos/download-breaking-bad-season-1-5-dual-audio-hindi-english-720p-1080p-bluray-esubs/'
    ]
    
    for url in test_urls:
        print(f"\n==========================================")
        print(f"Fetching: {url}")
        resp = client.get(url)
        if resp.status_code != 200:
            print("Status:", resp.status_code)
            continue
        soup = BeautifulSoup(resp.text, 'html.parser')
        title = soup.select_one('h1.entry-title, h1')
        print("Title:", title.get_text(strip=True) if title else "N/A")
        content = soup.select_one('.entry-content')
        if not content:
            continue
        
        # Look for buttons / links
        for a in content.select('a'):
            href = a.get('href', '')
            text = a.get_text(strip=True)
            if not href or href.startswith('#') or 'uhdmovies.autos/wp-' in href:
                continue
            parent = a.find_parent(['p', 'div', 'h3', 'h4'])
            p_text = parent.get_text(strip=True) if parent else ""
            if any(k in href for k in ['unblockedgames', 'cloud.', 'driveseed', 'hubcloud', 'techmny', 'drive', 'gamerx', 'links', 'go.']) or any(q in text.lower() for q in ['1080p', '2160p', '4k', '720p', 'download', 'episode', 'gdrive', 'seed', 'hub']):
                print(f"  [Link] '{text}' -> {href} | Context: {p_text[:80]}")

if __name__ == '__main__':
    inspect_urls()
