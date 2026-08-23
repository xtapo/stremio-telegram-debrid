import httpx
from bs4 import BeautifulSoup
import re

client = httpx.Client(headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}, follow_redirects=True, timeout=20)

def parse_post(url):
    resp = client.get(url)
    soup = BeautifulSoup(resp.text, 'html.parser')
    content = soup.select_one('.entry-content')
    if not content:
        return []
    
    streams = []
    # Iterate over elements in entry-content
    # Typical UHDMovies structure:
    # 1. A heading or paragraph describing quality/format, e.g. "Avatar (2022) 2160p MA WEB-DL... [14GB]"
    # 2. Followed by a Download button/link (G-Drive / Instant / Episodes)
    
    current_title = ""
    current_season = None
    
    for el in content.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'div', 'hr']):
        text = el.get_text(" ", strip=True)
        
        # Check if this element defines a quality / stream title or season
        season_match = re.search(r'Season\s*(\d+)', text, re.I)
        if season_match and ('season' in text.lower() or 'episode' in text.lower()):
            current_season = int(season_match.group(1))
            
        # Look for links inside this element
        links = el.find_all('a')
        for a in links:
            href = a.get('href', '')
            a_text = a.get_text(strip=True)
            if not href or href.startswith('#') or 'uhdmovies' in href and not '/?sid=' in href:
                continue
            if 'unblockedgames' in href or 'driveseed' in href or 'hubcloud' in href or 'techmny' in href or 'cloud.' in href or '/?sid=' in href or 'drive' in href:
                # Check episode number
                ep_match = re.search(r'Episode\s*(\d+)|Ep\s*(\d+)|E(\d+)', a_text, re.I)
                ep_num = int(ep_match.group(1) or ep_match.group(2) or ep_match.group(3)) if ep_match else None
                
                streams.append({
                    'title': text if text != a_text else current_title,
                    'btn_text': a_text,
                    'url': href,
                    'season': current_season,
                    'episode': ep_num
                })
        
        if any(q in text.lower() for q in ['2160p', '1080p', '720p', '4k', 'hevc', 'bluray', 'web-dl', 'hdr', 'remux']):
            current_title = text

    return streams

if __name__ == '__main__':
    for u in [
        'https://uhdmovies.autos/download-interstellar-2014-dual-audio-hindi-english-2160p-4k-1080p-x264-10bit-remux-hdr-dovi-hevc-bluray-esubs/',
        'https://uhdmovies.autos/download-dune-prophecy-2024-season-1-s01e01-added-dual-audio-hindi-english-2160p-4k-1080p-1080p-10bit-x264-hevc-hdr-dovi-web-dl-esubs/'
    ]:
        print(f"\nParsing: {u}")
        res = parse_post(u)
        print(f"Found {len(res)} stream items:")
        for r in res[:10]:
            print(" ->", r)
