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
    print("[1] GET", url)
    r1 = await client.get(url)
    soup1 = BeautifulSoup(r1.text, "html.parser")
    form1 = soup1.select_one("form")
    action1 = form1.get("action") or str(r1.url)
    if not action1.startswith("http"):
        action1 = urllib.parse.urljoin(str(r1.url), action1)
    data1 = {inp.get("name"): inp.get("value", "") for inp in form1.select("input") if inp.get("name")}

    print("[2] POST", action1, data1)
    r2 = await client.post(action1, data=data1, headers={"Referer": str(r1.url)})
    soup2 = BeautifulSoup(r2.text, "html.parser")
    form2 = soup2.select_one("form")
    action2 = form2.get("action") or str(r2.url)
    if not action2.startswith("http"):
        action2 = urllib.parse.urljoin(str(r2.url), action2)
    data2 = {inp.get("name"): inp.get("value", "") for inp in form2.select("input") if inp.get("name")}

    print("[3] POST", action2, data2)
    r3 = await client.post(action2, data=data2, headers={"Referer": str(r2.url)})

    match_cookie = re.search(r"s_\d+\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", r3.text)
    match_go = re.search(r"https?://[^'\"\s]+/\?go=([^'\"\s]+)", r3.text)

    c_name, c_val = match_cookie.groups()
    go_param = match_go.group(1)
    base_domain = urllib.parse.urlsplit(str(r3.url)).netloc
    go_url = f"https://{base_domain}/?go={go_param}"
    client.cookies.set(c_name, c_val, domain=base_domain)

    print("[4] GET go_url:", go_url)
    r4 = await client.get(go_url, headers={"Referer": str(r3.url), "Cookie": f"{c_name}={c_val}"})
    print("r4 status:", r4.status_code, "URL:", r4.url)
    print("r4 text:\n", r4.text)

    meta_refresh = re.search(r'content=["\']\d+;\s*url=([^"\']+)["\']', r4.text, re.I)
    loc_match = re.search(r'window\.location\.(?:replace|href)\s*=\s*["\']([^"\']+)["\']', r4.text)
    target_url = meta_refresh.group(1) if meta_refresh else (loc_match.group(1) if loc_match else None)
    print("target_url:", target_url)

    if target_url:
        print("[5] GET target_url:", target_url)
        r5 = await client.get(target_url, headers={"Referer": str(r4.url)})
        print("r5 status:", r5.status_code, "URL:", r5.url)
        file_match = re.search(r'window\.location\.replace\(["\']([^"\']+)["\']\)', r5.text)
        driveseed_file = urllib.parse.urljoin(str(r5.url), file_match.group(1)) if file_match else str(r5.url)
        print("driveseed_file:", driveseed_file)

        print("[6] GET driveseed_file:", driveseed_file)
        r6 = await client.get(driveseed_file, headers={"Referer": str(r5.url)})
        soup6 = BeautifulSoup(r6.text, "html.parser")
        for a in soup6.select("a[href]"):
            print("  Drive link:", a.get_text(strip=True), "->", a.get("href"))

asyncio.run(run())
