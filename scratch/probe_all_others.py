import requests
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Referer': 'https://google.com'
}

def probe(url, name):
    try:
        r = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
        print(f"[{name}] status: {r.status_code}, url: {r.url}, len: {len(r.text)}")
    except Exception as e:
        print(f"[{name}] error: {e}")

probe("https://onflix.lat/movies?category=phim-bo", "Onflix")
probe("https://k8s.onflixcdn.com/api/movies", "Onflix API")
probe("https://phimhdcss.com", "PhimHDCS")
probe("https://yumei-anime.com", "YumeiAnime")
probe("https://hdvnn.xyz", "HDVNN")
probe("https://1phim22.com", "PhimDinhCao")
probe("https://phimlongtieng.link", "PhimLongTieng")
probe("https://phimsea.com", "PhimSea")
