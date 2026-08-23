import asyncio
import httpx
from bs4 import BeautifulSoup

async def check():
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        # Home
        r_home = await client.get("https://4khdhub.one/")
        soup_home = BeautifulSoup(r_home.text, "html.parser")
        home_cards = soup_home.select("a.movie-card")
        print(f"Homepage cards: {len(home_cards)}")
        for c in home_cards[:5]:
            print("  ", c.get("href"), c.select_one(".movie-card-title, h2").get_text(strip=True) if c.select_one(".movie-card-title, h2") else "")

        # Category movies
        r_cat = await client.get("https://4khdhub.one/category/movies/")
        soup_cat = BeautifulSoup(r_cat.text, "html.parser")
        cat_cards = soup_cat.select("a.movie-card")
        print(f"Category /movies/ cards: {len(cat_cards)}")
        for c in cat_cards[:5]:
            print("  ", c.get("href"), c.select_one(".movie-card-title, h2").get_text(strip=True) if c.select_one(".movie-card-title, h2") else "")

asyncio.run(check())
