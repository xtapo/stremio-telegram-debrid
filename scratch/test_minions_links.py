import asyncio, httpx, re
from bs4 import BeautifulSoup

async def run():
    url = "https://gamerxyt.com/hubcloud.php?host=hubcloud&id=x7xe50ghgp8p97r&token=Uk9BdWp4VC9wZWVQNFBBZmc4Sk14Rk1EenBLejlnWGJ5ajdvemtESTgydz0="
    async with httpx.AsyncClient(headers={'User-Agent': 'Mozilla/5.0'}) as client:
        r = await client.get(url)
        soup = BeautifulSoup(r.text, "lxml")
        for a in soup.find_all("a", href=True):
            print(a.get_text(strip=True).encode('utf-8', 'ignore').decode('utf-8'), "->", a["href"])
        print("\n\nJS VARS:")
        for m in re.finditer(r'var\s+([a-zA-Z0-9_]+)\s*=\s*["\']([^"\']+)["\']', r.text):
            print(m.group(1), "=", m.group(2))

asyncio.run(run())
