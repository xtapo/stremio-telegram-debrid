import asyncio, re, urllib.parse, httpx
from bs4 import BeautifulSoup

url = "https://cloud.unblockedgames.world/?sid=a3Y4azk3STZ5RVphb1c0d0pkeDllaWVjc3NTd1dyeHJZSlNRUk9wY2NMVXRQVkZ2NmRhMWd5Ymdycmx3cW4yNQ=="
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://uhdmovies.autos/",
    "Accept-Language": "en-US,en;q=0.9",
}

async def run():
    client = httpx.AsyncClient(follow_redirects=True, headers=headers, timeout=15.0)
    r1 = await client.get(url)
    print("r1 cookies:", dict(client.cookies))

    soup1 = BeautifulSoup(r1.text, "html.parser")
    form1 = soup1.select_one("form")
    action1 = form1.get("action") or str(r1.url)
    data1 = {inp.get("name"): inp.get("value", "") for inp in form1.select("input") if inp.get("name")}

    r2 = await client.post(action1, data=data1, headers={"Referer": str(r1.url)})
    print("r2 cookies:", dict(client.cookies))

    soup2 = BeautifulSoup(r2.text, "html.parser")
    form2 = soup2.select_one("form")
    action2 = form2.get("action") or str(r2.url)
    data2 = {inp.get("name"): inp.get("value", "") for inp in form2.select("input") if inp.get("name")}

    r3 = await client.post(action2, data=data2, headers={"Referer": str(r2.url)})
    print("r3 cookies:", dict(client.cookies))

    match_cookie = re.search(r"s_\d+\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", r3.text)
    match_go = re.search(r"https?://[^'\"\s]+/\?go=([^'\"\s]+)", r3.text)

    c_name, c_val = match_cookie.groups()
    go_param = match_go.group(1)
    base_domain = urllib.parse.urlsplit(str(r3.url)).netloc
    go_url = f"https://{base_domain}/?go={go_param}"

    # Set cookie in client jar with domain and path
    client.cookies.set(c_name, c_val, domain=base_domain, path="/")
    client.cookies.set(c_name, c_val, domain="." + base_domain, path="/")
    client.cookies.set(c_name, c_val)

    cookie_header = "; ".join([f"{k}={v}" for k, v in client.cookies.items()])
    print("All cookies in jar:", dict(client.cookies))
    print("Cookie header:", cookie_header)

    r4 = await client.get(go_url, headers={"Referer": str(r3.url), "Cookie": cookie_header})
    print("r4 status:", r4.status_code)
    print("r4 text:\n", r4.text[:600])

asyncio.run(run())
