import asyncio
import re
import urllib.parse
import httpx
from bs4 import BeautifulSoup

url = "https://cloud.unblockedgames.world/?sid=aDBQeDhZNVBsY1I5cVlWUzJJM1pvdXc0TTc5dzN0YVZFWFVXWHVtU0NhL0pSYVkrQ051NjVTaWlpYm05OXkwaw=="

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://uhdmovies.autos/",
    "Accept-Language": "en-US,en;q=0.9",
}

async def debug_resolver():
    client = httpx.AsyncClient(follow_redirects=True, headers=headers, timeout=15.0)
    
    print("[1] GET", url)
    r1 = await client.get(url)
    print("  -> Status:", r1.status_code, "URL:", r1.url, "Text len:", len(r1.text))
    soup1 = BeautifulSoup(r1.text, "html.parser")
    form1 = soup1.select_one("form")
    if not form1:
        print("  ❌ No form 1 found in HTML!")
        print("  Snippet:", r1.text[:500])
        return
    
    action1 = form1.get("action") or str(r1.url)
    if not action1.startswith("http"):
        action1 = urllib.parse.urljoin(str(r1.url), action1)
    data1 = {inp.get("name"): inp.get("value", "") for inp in form1.select("input") if inp.get("name")}
    print("  -> Form 1 action:", action1, "data:", data1)

    print("\n[2] POST", action1)
    r2 = await client.post(action1, data=data1, headers={"Referer": str(r1.url)})
    print("  -> Status:", r2.status_code, "URL:", r2.url, "Text len:", len(r2.text))
    soup2 = BeautifulSoup(r2.text, "html.parser")
    form2 = soup2.select_one("form")
    if not form2:
        print("  ❌ No form 2 found in HTML!")
        print("  Snippet:", r2.text[:500])
        return

    action2 = form2.get("action") or str(r2.url)
    if not action2.startswith("http"):
        action2 = urllib.parse.urljoin(str(r2.url), action2)
    data2 = {inp.get("name"): inp.get("value", "") for inp in form2.select("input") if inp.get("name")}
    print("  -> Form 2 action:", action2, "data:", data2)

    print("\n[3] POST", action2)
    r3 = await client.post(action2, data=data2, headers={"Referer": str(r2.url)})
    print("  -> Status:", r3.status_code, "URL:", r3.url, "Text len:", len(r3.text))

    print("r3 text snippet:\n", r3.text[:1500])

    match_cookie = re.search(r"s_\d+\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", r3.text)
    match_go = re.search(r"https?://[^'\"\s]+/\?go=([^'\"\s]+)", r3.text)
    print("  -> match_cookie:", match_cookie.groups() if match_cookie else None)
    print("  -> match_go:", match_go.group(1) if match_go else None)

    if not match_cookie or not match_go:
        return

    c_name, c_val = match_cookie.groups()
    go_param = match_go.group(1)
    base_domain = urllib.parse.urlsplit(str(r3.url)).netloc
    go_url = f"https://{base_domain}/?go={go_param}"
    client.cookies.set(c_name, c_val, domain=base_domain)

    print("\n[4] GET go_url:", go_url)
    r4 = await client.get(go_url, headers={"Referer": str(r3.url)})
    print("r4 text:\n", r4.text)

    if not target_url:
        print("  ❌ No redirect target from r4!")
        print("  Snippet:", r4.text[:1000])
        return

    print("\n[5] GET target_url:", target_url)
    r5 = await client.get(target_url, headers={"Referer": str(r4.url)})
    print("  -> Status:", r5.status_code, "URL:", r5.url, "Text len:", len(r5.text))

    file_match = re.search(r'window\.location\.replace\(["\']([^"\']+)["\']\)', r5.text)
    if file_match:
        rel = file_match.group(1)
        driveseed_file_url = urllib.parse.urljoin(str(r5.url), rel)
    else:
        driveseed_file_url = str(r5.url)
    print("  -> driveseed_file_url:", driveseed_file_url)

    print("\n[6] GET driveseed_file_url:", driveseed_file_url)
    r6 = await client.get(driveseed_file_url, headers={"Referer": str(r5.url)})
    print("  -> Status:", r6.status_code, "URL:", r6.url, "Text len:", len(r6.text))
    soup6 = BeautifulSoup(r6.text, "html.parser")
    for a in soup6.select("a[href]"):
        print("     Link:", a.get_text(strip=True), "->", a.get("href"))

if __name__ == "__main__":
    asyncio.run(debug_resolver())
