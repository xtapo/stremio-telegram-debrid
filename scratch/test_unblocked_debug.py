import asyncio
import httpx
from bs4 import BeautifulSoup
import re
import urllib.parse

url = "https://cloud.unblockedgames.world/?sid=aDBQeDhZNVBsY1I5cVlWUzJJM1pvc3lPMUw2ZjY1MzZjQ0s2MnFuM3BQS3B1R2w1ZjhIY1NXKzhXbEVsMjVsbg=="

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://uhdmovies.autos/",
    "Accept-Language": "en-US,en;q=0.9",
}

async def debug_unblocked():
    client = httpx.AsyncClient(follow_redirects=True, headers=headers, timeout=20.0)
    print("Step 1: GET", url)
    r1 = await client.get(url)
    print("  Status:", r1.status_code, "URL:", r1.url)
    print("  Body sample:", r1.text[:500])
    
    soup1 = BeautifulSoup(r1.text, "html.parser")
    form1 = soup1.select_one("form")
    print("  Form 1:", form1)
    if form1:
        action1 = form1.get("action") or str(r1.url)
        data1 = {inp.get("name"): inp.get("value", "") for inp in form1.select("input") if inp.get("name")}
        print("  action1:", action1, "data1:", data1)
        print("Step 2: POST form 1 to", action1)
        r2 = await client.post(action1, data=data1, headers={"Referer": str(r1.url)})
        print("  Status:", r2.status_code, "URL:", r2.url)
        print("  Body sample:", r2.text[:500])
        soup2 = BeautifulSoup(r2.text, "html.parser")
        form2 = soup2.select_one("form")
        print("  Form 2:", form2)
        if form2:
            action2 = form2.get("action") or str(r2.url)
            data2 = {inp.get("name"): inp.get("value", "") for inp in form2.select("input") if inp.get("name")}
            print("  action2:", action2, "data2:", data2)
            print("Step 3: POST form 2 to", action2)
            r3 = await client.post(action2, data=data2, headers={"Referer": str(r2.url)})
            print("  Status:", r3.status_code, "URL:", r3.url)
            with open("scratch/r3.html", "w", encoding="utf-8") as f:
                f.write(r3.text)
            print("Wrote scratch/r3.html (length %d)" % len(r3.text))
            
            match_cookie = re.search(r"s_\d+\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", r3.text)
            match_go = re.search(r"https?://[^'\"\s]+/\?go=([^'\"\s]+)", r3.text)
            print("  match_cookie:", match_cookie.groups() if match_cookie else None)
            print("  match_go:", match_go.group(1) if match_go else None)

            if not match_cookie or not match_go:
                print("Missing cookie or go!")
                return

            c_name, c_val = match_cookie.groups()
            go_param = match_go.group(1)
            base_domain = urllib.parse.urlsplit(str(r3.url)).netloc
            go_url = f"https://{base_domain}/?go={go_param}"

            print("Cookie name:", c_name)
            print("Cookie val:", c_val)
            client.cookies.set(c_name, c_val)

            print("Waiting 10 seconds before requesting go_url...")
            await asyncio.sleep(10)

            print("Step 4: GET go_url:", go_url)
            r4 = await client.get(go_url, headers={"Referer": str(r3.url)})
            print("  Status:", r4.status_code, "URL:", r4.url)
            print("  r4 body:\n", r4.text)



            target_url = None
            meta_refresh = re.search(r'content=["\']\d+;\s*url=([^"\']+)["\']', r4.text, re.I)
            if meta_refresh:
                target_url = meta_refresh.group(1)
            else:
                loc_match = re.search(r'window\.location\.(?:replace|href)\s*=\s*["\']([^"\']+)["\']', r4.text)
                if loc_match:
                    target_url = loc_match.group(1)

            print("  target_url:", target_url)
            if not target_url:
                return

            print("Step 5: GET target_url:", target_url)
            r5 = await client.get(target_url, headers={"Referer": str(r4.url)})
            print("  Status:", r5.status_code, "URL:", r5.url)
            print("  r5 body:\n", r5.text[:1000])

            file_match = re.search(r'window\.location\.replace\(["\']([^"\']+)["\']\)', r5.text)
            if file_match:
                rel = file_match.group(1)
                driveseed_file_url = urllib.parse.urljoin(str(r5.url), rel)
            else:
                driveseed_file_url = str(r5.url)
            print("  driveseed_file_url:", driveseed_file_url)

            print("Step 6: GET driveseed_file_url:", driveseed_file_url)
            r6 = await client.get(driveseed_file_url, headers={"Referer": str(r5.url)})
            print("  Status:", r6.status_code, "URL:", r6.url)
            print("  r6 body:\n", r6.text[:1000])

            soup6 = BeautifulSoup(r6.text, "html.parser")
            for a in soup6.select("a[href]"):
                print("  Link in r6:", a.get_text(strip=True), "->", a.get("href"))



asyncio.run(debug_unblocked())
