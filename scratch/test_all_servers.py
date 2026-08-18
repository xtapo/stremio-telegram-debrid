import httpx
import re
from bs4 import BeautifulSoup
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://hdtoday.sc/'
}
client = httpx.Client(headers=headers, timeout=15.0, follow_redirects=True)

# Test movie Hotel Desire (82023) or Avatar (19995)
tmdb_id = "19995"

# 1. Test VidUp (UpCloud)
r_vidup = client.get(f"https://vidup.to/movie/{tmdb_id}")
print("=== VidUp ===")
print("Status:", r_vidup.status_code, "Len:", len(r_vidup.text))
soup_vidup = BeautifulSoup(r_vidup.text, "html.parser")
for s in soup_vidup.find_all("script"):
    if s.get("src"):
        src = s.get("src")
        # download page chunks
        if "movie" in src or "page" in src or "app" in src or "layout" in src:
            chunk_url = "https://vidup.to" + src if src.startswith("/") else src
            r_c = client.get(chunk_url)
            print("VidUp chunk:", src, "->", re.findall(r"https?://[a-zA-Z0-9_\-\./]+|/api/[a-zA-Z0-9_\-\./]+", r_c.text))

# 2. Test MoviesAPI (MegaCloud)
r_moviesapi = client.get(f"https://moviesapi.to/movie/{tmdb_id}")
print("\n=== MoviesAPI ===")
print("Status:", r_moviesapi.status_code, "Len:", len(r_moviesapi.text))
for s in re.findall(r"<script[^>]*>(.*?)</script>", r_moviesapi.text, re.DOTALL):
    if "token" in s or "source" in s or "m3u8" in s or "player" in s or "fetch" in s:
        print("MoviesAPI script:", s[:300])

# 3. Test PrimeSrc
r_primesrc = client.get(f"https://primesrc.me/embed/movie?tmdb={tmdb_id}")
print("\n=== PrimeSrc ===")
print("Status:", r_primesrc.status_code, "Len:", len(r_primesrc.text))
print("PrimeSrc HTML:\n", r_primesrc.text[:1000])

# 4. Test VidLove
r_vidlove = client.get(f"https://player.vidlove.cc/embed/movie/{tmdb_id}")
print("\n=== VidLove ===")
print("Status:", r_vidlove.status_code, "Len:", len(r_vidlove.text))
print("VidLove HTML:\n", r_vidlove.text[:1000])

# 5. Test VidSrcme (AKCloud)
r_vidsrc = client.get(f"https://vidsrcme.ru/embed/movie?tmdb={tmdb_id}")
print("\n=== VidSrcme ===")
print("Status:", r_vidsrc.status_code, "Len:", len(r_vidsrc.text))
for ifr in BeautifulSoup(r_vidsrc.text, "html.parser").find_all("iframe"):
    print("VidSrcme iframe:", ifr.get("src"))
