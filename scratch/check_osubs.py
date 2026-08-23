import asyncio
import httpx
import urllib.parse

async def check():
    # 1. With filename extra
    url1 = "https://opensubtitles-v3.strem.io/subtitles/movie/tt26657236/filename=backrooms.movie.7787.mkv.json"
    # 2. Without extra
    url2 = "https://opensubtitles-v3.strem.io/subtitles/movie/tt26657236.json"

    async with httpx.AsyncClient() as client:
        r1 = await client.get(url1)
        r2 = await client.get(url2)
        print("With custom filename extra count:", len(r1.json().get("subtitles", [])))
        print("Without extra (pure IMDb ID) count:", len(r2.json().get("subtitles", [])))
        for s in r2.json().get("subtitles", [])[:5]:
            print(" ", s.get("lang"), s.get("id"), s.get("url")[:50])

asyncio.run(check())
