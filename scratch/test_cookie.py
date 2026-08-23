import asyncio, re, urllib.parse, httpx
from bs4 import BeautifulSoup

url = "https://cloud.unblockedgames.world/?sid=aDBQeDhZNVBsY1I5cVlWUzJJM1pvdXc0TTc5dzN0YVZFWFVXWHVtU0NhL0pSYVkrQ051NjVTaWlpYm05OXkwaw=="
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://uhdmovies.autos/",
    "Accept-Language": "en-US,en;q=0.9",
}

async def test_cookie():
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

    match_cookie = re.search(r"s_\d+\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", r3.text)
    match_go = re.search(r"https?://[^'\"\s]+/\?go=([^'\"\s]+)", r3.text)

    c_name, c_val = match_cookie.groups()
    go_param = match_go.group(1)
    base_domain = urllib.parse.urlsplit(str(r3.url)).netloc
    go_url = f"https://{base_domain}/?go={go_param}"

    print(f"Cookie: {c_name}={c_val}")
    print(f"Go URL: {go_url}")

    req_headers = {
        "User-Agent": headers["User-Agent"],
        "Referer": str(r3.url),
        "Cookie": f"{c_name}={c_val}",
    }

    r4 = await client.get(go_url, headers=req_headers)
    print("r4 without delay:", r4.text[:400])

    print("Waiting 5 seconds...")
    await asyncio.sleep(5)
    r4_delayed = await client.get(go_url, headers=req_headers)
    print("r4 with 5s delay:", r4_delayed.text[:400])

asyncio.run(test_cookie())
