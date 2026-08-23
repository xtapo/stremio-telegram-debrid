import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import re
import urllib.parse
import httpx
from bs4 import BeautifulSoup
from vidking_router import VIDKING_SERVERS, fetch_and_decrypt_server, get_vidking_seed, vidking_fetch_tmdb_json

async def resolve_m2w_streams(media_type: str, slug: str, season: int = 1, episode: int = 1, base_url: str = "http://localhost:7860"):
    m2w_base = "https://movies2watch.vc"
    page_url = f"{m2w_base}/series/{slug}/{season}-{episode}/" if media_type == "series" else f"{m2w_base}/movie/{slug}/"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": m2w_base,
    }
    
    found_imdb_id = None
    found_tmdb_id = None
    title = slug.replace("-", " ").title()
    year = ""
    embed_servers = []
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15) as client:
        r = await client.get(page_url)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            h_name = soup.select_one("h2.heading-name a, h2.heading-name")
            if h_name:
                title = h_name.text.strip()
            y_m = re.search(r"Released:\s*(\d{4})", r.text)
            if y_m:
                year = y_m.group(1)
            
            pl_m = re.search(r"const pl_url = ['\"]([^'\"]+)['\"]", r.text)
            if pl_m:
                pl_res = await client.get(pl_m.group(1), headers={"Referer": page_url})
                if pl_res.status_code == 200:
                    pl_soup = BeautifulSoup(pl_res.text, "html.parser")
                    for a_srv in pl_soup.select("a.sv-item, a[data-srv]"):
                        s_name = a_srv.get("data-srv") or a_srv.get("title") or "Server"
                        e_url = a_srv.get("data-id") or ""
                        if e_url and e_url.startswith("http"):
                            embed_servers.append((s_name, e_url))
                            
                            if not found_imdb_id:
                                imdb_m = re.search(r"(tt\d+)", e_url)
                                if imdb_m:
                                    found_imdb_id = imdb_m.group(1)
                            if not found_tmdb_id:
                                tmdb_m = re.search(r"/movie/(\d+)|/tv/(\d+)|/(\d{4,8})/", e_url)
                                if tmdb_m:
                                    val = tmdb_m.group(1) or tmdb_m.group(2) or tmdb_m.group(3)
                                    if val and len(val) >= 4:
                                        found_tmdb_id = int(val)
        
        # If TMDB ID not found from embeds, search TMDB by title
        if not found_tmdb_id:
            clean_q = re.sub(r"-\d+$", "", slug).replace("-", " ")
            tmdb_type = "movie" if media_type == "movie" else "tv"
            params = {"query": clean_q}
            if year:
                params["year" if tmdb_type == "movie" else "first_air_date_year"] = year
            s_data = await vidking_fetch_tmdb_json(f"/search/{tmdb_type}", params=params)
            results = s_data.get("results", []) if s_data else []
            if results:
                found_tmdb_id = int(results[0]["id"])
                if not year and (results[0].get("release_date") or results[0].get("first_air_date")):
                    year = (results[0].get("release_date") or results[0].get("first_air_date"))[:4]
                    
    print(f"[{media_type.upper()}] Title: {title} | Year: {year} | TMDB ID: {found_tmdb_id} | IMDb ID: {found_imdb_id}")
    
    streams = []
    # Fetch playable streams via Vidking engine if TMDB ID resolved
    if found_tmdb_id:
        seed = await get_vidking_seed(found_tmdb_id)
        if seed:
            for srv in VIDKING_SERVERS[:3]:
                srv_streams = await fetch_and_decrypt_server(
                    server_cfg=srv,
                    tmdb_id=found_tmdb_id,
                    media_type="tv" if media_type == "series" else "movie",
                    title=title,
                    year=year,
                    imdb_id=found_imdb_id or "",
                    season=season,
                    episode=episode,
                    seed=seed,
                    base_url=base_url
                )
                for st in srv_streams:
                    orig_n = st.get("name", "")
                    st["name"] = orig_n.replace("Vidking", "Movies2Watch HD")
                    streams.append(st)
                    
    # Add external web embed fallback
    for s_name, e_url in embed_servers:
        streams.append({
            "name": f"Movies2Watch\n🌐 {s_name}",
            "title": f"🎬 {title}\n🌐 Mở Trình Duyệt Web (Máy chủ {s_name})\n🚀 0% Băng thông máy chủ | Nhấp để mở",
            "externalUrl": e_url
        })
        
    print(f"Total streams generated: {len(streams)}")
    for s in streams[:4]:
        print(f" - {s.get('name').replace(chr(10), ' ')} -> {'URL: ' + s.get('url')[:60] if s.get('url') else 'External: ' + s.get('externalUrl')}")

async def main():
    print("=== Testing Movies2Watch Stream Flow ===")
    await resolve_m2w_streams("movie", "oppenheimer-51311")
    print()
    await resolve_m2w_streams("series", "avatar-the-last-airbender-67006", season=1, episode=1)

if __name__ == "__main__":
    asyncio.run(main())
