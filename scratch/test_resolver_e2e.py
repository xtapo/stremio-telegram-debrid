import httpx
from bs4 import BeautifulSoup
import re
import urllib.parse

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def resolve_unblocked_link(url: str, timeout: float = 15.0) -> list[dict]:
    """
    Walks:
    1. GET cloud.unblockedgames.world/?sid=... (or similar)
    2. POST form -> second page
    3. POST form2 -> third page
    4. Extract cookie & go url -> GET go url
    5. Follow redirect (meta refresh / window.location) -> driveseed.org
    6. On driveseed.org -> follow window.location.replace('/file/...')
    7. On driveseed file page -> extract direct instant download link
    8. Extract real streamable URL from instant download link!
    """
    client = httpx.Client(
        headers={"User-Agent": USER_AGENT, "Referer": "https://uhdmovies.autos/"},
        follow_redirects=True,
        timeout=timeout
    )
    
    # Step 1: GET landing
    r1 = client.get(url)
    soup1 = BeautifulSoup(r1.text, "html.parser")
    form1 = soup1.select_one("form")
    if not form1:
        # Check direct redirect
        return [{"url": str(r1.url), "name": "Direct"}]
        
    action1 = form1.get("action") or url
    data1 = {inp.get("name"): inp.get("value", "") for inp in form1.select("input") if inp.get("name")}
    
    # Step 2: POST form 1
    r2 = client.post(action1, data=data1, headers={"Referer": url})
    soup2 = BeautifulSoup(r2.text, "html.parser")
    form2 = soup2.select_one("form")
    if not form2:
        return []
    action2 = form2.get("action") or str(r2.url)
    data2 = {inp.get("name"): inp.get("value", "") for inp in form2.select("input") if inp.get("name")}
    
    # Step 3: POST form 2
    r3 = client.post(action2, data=data2, headers={"Referer": str(r2.url)})
    
    # Step 4: Cookie & go url
    match_cookie = re.search(r"s_\d+\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", r3.text)
    match_go = re.search(r"https?://[^'\"\s]+/\?go=([^'\"\s]+)", r3.text)
    
    if not match_cookie or not match_go:
        return []
        
    c_name, c_val = match_cookie.groups()
    go_param = match_go.group(1)
    base_domain = urllib.parse.urlsplit(str(r3.url)).netloc
    go_url = f"https://{base_domain}/?go={go_param}"
    
    client.cookies.set(c_name, c_val, domain=base_domain)
    
    # Step 5: GET go_url -> check meta refresh
    r4 = client.get(go_url, headers={"Referer": str(r3.url)})
    print("R4 URL:", r4.url)
    print("R4 Text:\n", r4.text[:300])
    
    target_url = None
    meta_refresh = re.search(r'content=["\']\d+;\s*url=([^"\']+)["\']', r4.text, re.I)
    if meta_refresh:
        target_url = meta_refresh.group(1)
    else:
        loc_match = re.search(r'window\.location\.(?:replace|href)\s*=\s*["\']([^"\']+)["\']', r4.text)
        if loc_match:
            target_url = loc_match.group(1)
            
    print("Extracted target_url:", target_url)
    if not target_url:
        return []
        
    # Step 6: Follow target URL (e.g. driveseed.org/r?key=...)
    r5 = client.get(target_url, headers={"Referer": str(r4.url)})
    print("R5 URL:", r5.url)
    print("R5 text:\n", r5.text[:300])
    
    driveseed_file_url = None
    file_match = re.search(r'window\.location\.replace\(["\']([^"\']+)["\']\)', r5.text)
    if file_match:
        rel = file_match.group(1)
        driveseed_file_url = urllib.parse.urljoin(str(r5.url), rel)
    else:
        driveseed_file_url = str(r5.url)
        
    print("Driveseed file URL:", driveseed_file_url)
    # Step 7: On file page, extract instant download or resume cloud link
    r6 = client.get(driveseed_file_url, headers={"Referer": str(r5.url)})
    print("R6 URL:", r6.url)
    print("R6 Status:", r6.status_code)
    soup6 = BeautifulSoup(r6.text, "html.parser")
    
    results = []
    for a in soup6.select("a[href]"):
        btn_text = a.get_text(strip=True)
        href = a.get("href")
        if not href:
            continue
        if "login" in href.lower() or href.startswith("#"):
            continue
        if any(k in btn_text.lower() for k in ["instant download", "resume cloud", "direct download", "download", "stream"]):
            results.append({"name": btn_text, "href": href})
            
    return results

if __name__ == '__main__':
    test_urls = [
        # Movie 4K
        'https://cloud.unblockedgames.world/?sid=a3Y4azk3STZ5RVphb1c0d0pkeDllaWVjc3NTd1dyeHJZSlNRUkszSnJFSGphampKSXNSZWwrcG5LYTJEYkE2UkZIZjJJc3VDQ1hhdW9jVTJmTTFzU29PMlFKZ0MzTmhvSC9NWEh6a0Z2T2NUZWYxVHliWkxuMnRrRS9CSUt4MFRFNG8zT1diaGJVdmhJY1c5R3FjOXpTclF1Zno3NXIxMjJ0cnZheEl5bzlac3FLdmRTRTB0SXU3WFMycTQyNjhHcndML1V5Ujg2ZkVSSjhRSlVWMmV3MmoxNmJrMU9OdlZyNHBMUTZKSkg5czVrYTUrNmduTGNMeW5LeXhUQWViOQ==',
        # TV Ep 1
        'https://cloud.unblockedgames.world/?sid=a3Y4azk3STZ5RVphb1c0d0pkeDllaWVjc3NTd1dyeHJZSlNRUkszSnJFSGphampKSXNSZWwrcG5LYTJEYkE2UkZIZjJJc3VDQ1hhdW9jVTJmTTFzU29PMlFKZ0MzTmhvSC9NWEh6a0Z2T2VSZTU3SGVrNkVWdy9ML0YxQ0FieDkxY29IZWp5bVF4M0c4M2lIZk5EUWRsaG8rWWRTbmpOZVlCcitRSkpyMXlYc3ltbjZMcUU0TFZNNzlEZXVDRm9kRlpzRkI1ZVcwQXJWa0J0S3k1YU9vS1NGazJQa0crbGh2N2hZYjh2cU14VEZmZE55Nmpta1lOR0lZaktub2MvLw=='
    ]
    
    for u in test_urls:
        print(f"\nResolving: {u[:60]}...")
        links = resolve_unblocked_link(u)
        print("Resolved results:", links)
