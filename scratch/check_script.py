import asyncio, re, urllib.parse, httpx
from bs4 import BeautifulSoup

url = "https://cloud.unblockedgames.world/?sid=aDBQeDhZNVBsY1I5cVlWUzJJM1pvdXc0TTc5dzN0YVZFWFVXWHVtU0NhL0pSYVkrQ051NjVTaWlpYm05OXkwaw=="
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://uhdmovies.autos/",
    "Accept-Language": "en-US,en;q=0.9",
}

async def check():
    client = httpx.AsyncClient(follow_redirects=True, headers=headers, timeout=15.0)
    r1 = await client.get(url)
    soup1 = BeautifulSoup(r1.text, "html.parser")
    form1 = soup1.select_one("form")
    action1 = form1.get("action") or str(r1.url)
    if not action1.startswith("http"):
        action1 = urllib.parse.urljoin(str(r1.url), action1)
    data1 = {inp.get("name"): inp.get("value", "") for inp in form1.select("input") if inp.get("name")}

    r2 = await client.post(action1, data=data1, headers={"Referer": str(r1.url)})
    soup2 = BeautifulSoup(r2.text, "html.parser")
    form2 = soup2.select_one("form")
    action2 = form2.get("action") or str(r2.url)
    if not action2.startswith("http"):
        action2 = urllib.parse.urljoin(str(r2.url), action2)
    data2 = {inp.get("name"): inp.get("value", "") for inp in form2.select("input") if inp.get("name")}

    r3 = await client.post(action2, data=data2, headers={"Referer": str(r2.url)})
    soup3 = BeautifulSoup(r3.text, "html.parser")
    for s in soup3.select("script"):
        if s.string and ("s_" in s.string or "cookie" in s.string or "?go=" in s.string or "location" in s.string):
            print("=== SCRIPT ===")
            print(s.string)

asyncio.run(check())
