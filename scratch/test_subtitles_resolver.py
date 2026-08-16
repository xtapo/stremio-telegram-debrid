import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import httpx
import re
import urllib.parse

async def find_imdb_for_moviesdrive_id(type: str, md_id: str):
    # Example md_id: moviesdrive:minions-monsters-2026-web-dl-hindi-dd5-1-english-480p-720p-1080p-2160p-4k-sdr-x264-esubs-full-movie
    parts = md_id.split(":")
    slug = parts[1]
    season = int(parts[2]) if len(parts) > 2 else 1
    episode = int(parts[3]) if len(parts) > 3 else 1
    
    # Extract title and year from slug
    # Remove quality words: web-dl, hindi, english, 480p, 720p, 1080p, 2160p, 4k, sdr, x264, esubs, full-movie, season-1
    clean = slug
    for w in ['web-dl', 'hindi', 'dd5-1', 'english', '480p', '720p', '1080p', '2160p', '4k', 'sdr', 'x264', 'esubs', 'full-movie', 'esub']:
        clean = re.sub(rf'\b{w}\b', '', clean, flags=re.I)
    
    # Extract year if any
    year_match = re.search(r'\b(19\d\d|20\d\d)\b', clean)
    clean_title = re.sub(r'\b(19\d\d|20\d\d)\b', '', clean)
    clean_title = re.sub(r'season-\d+', '', clean_title, flags=re.I)
    clean_title = clean_title.replace('-', ' ').strip()
    
    print(f"Searching Cinemeta for: '{clean_title}'...")
    cinemeta_url = f"https://v3-cinemeta.strem.io/catalog/{type}/top/search={urllib.parse.quote(clean_title)}.json"
    
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get(cinemeta_url)
        if resp.status_code == 200:
            metas = resp.json().get("metas", [])
            print(f"Found {len(metas)} Cinemeta results:")
            for m in metas[:3]:
                print(f" - {m.get('name')} ({m.get('year')}) => IMDb: {m.get('imdb_id') or m.get('id')}")
            if metas:
                imdb_id = metas[0].get('imdb_id') or metas[0].get('id')
                if type == "series":
                    return f"{imdb_id}:{season}:{episode}"
                return imdb_id
    return None

async def test():
    md_id = "moviesdrive:minions-monsters-2026-web-dl-hindi-dd5-1-english-480p-720p-1080p-2160p-4k-sdr-x264-esubs-full-movie"
    imdb_id = await find_imdb_for_moviesdrive_id("movie", md_id)
    print("Resolved IMDb ID:", imdb_id)
    
    if imdb_id:
        url = f"https://opensubtitles-v3.strem.io/subtitles/movie/{urllib.parse.quote(imdb_id)}.json"
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url)
            print("OpenSubtitles status:", resp.status_code)
            subs = resp.json().get("subtitles", [])
            print(f"Found {len(subs)} subtitles:")
            for s in subs[:5]:
                print(f" - Lang: {s.get('lang')} => {s.get('url')[:60]}...")

if __name__ == '__main__':
    asyncio.run(test())
