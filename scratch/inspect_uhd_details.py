import httpx
from bs4 import BeautifulSoup

client = httpx.Client(headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}, follow_redirects=True, timeout=20)

def test_movie():
    url = 'https://uhdmovies.autos/download-avatar-the-way-of-water-2022-dual-audio-hindi-english-2160p-4k-1080p-x264-hevc-hdr-dovi-web-dl-esubs/'
    resp = client.get(url)
    soup = BeautifulSoup(resp.text, 'html.parser')
    content = soup.select_one('.entry-content')
    print('=== MOVIE POST ===')
    for tag in content.children:
        if tag.name:
            txt = tag.get_text(strip=True)
            links = [(a.get_text(strip=True), a.get('href')) for a in tag.find_all('a')]
            if links or any(k in txt.lower() for k in ['download', '1080p', '2160p', '4k', '720p', 'hevc', 'hdr', 'gb']):
                print(f'<{tag.name} class="{tag.get("class")}"> : {txt[:100]}')
                for l in links:
                    print('   -->', l)

def test_tv():
    url = 'https://uhdmovies.autos/download-avatar-the-last-airbender-2024-season-1-hindi-1080p/'
    resp = client.get(url)
    soup = BeautifulSoup(resp.text, 'html.parser')
    content = soup.select_one('.entry-content')
    print('\n=== TV SHOW POST ===')
    for tag in content.children:
        if tag.name:
            txt = tag.get_text(strip=True)
            links = [(a.get_text(strip=True), a.get('href')) for a in tag.find_all('a')]
            if links or any(k in txt.lower() for k in ['download', 'season', 'episode', '1080p', '2160p', '4k', '720p', 'hevc', 'hdr', 'gb']):
                print(f'<{tag.name} class="{tag.get("class")}"> : {txt[:100]}')
                for l in links:
                    print('   -->', l)

if __name__ == '__main__':
    test_movie()
    test_tv()
