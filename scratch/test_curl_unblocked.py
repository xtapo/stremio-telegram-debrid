import re, urllib.parse, time
from bs4 import BeautifulSoup
from curl_cffi import requests

url = "https://cloud.unblockedgames.world/?sid=a3Y4azk3STZ5RVphb1c0d0pkeDllaWVjc3NTd1dyeHJZSlNRUk9wY2NMVXRQVkZ2NmRhMWd5Ymdycmx3cW4yNQ=="

def run_curl():
    session = requests.Session(impersonate="chrome120")
    
    print("[1] GET", url)
    r1 = session.get(url, headers={"Referer": "https://uhdmovies.autos/"})
    soup1 = BeautifulSoup(r1.text, "html.parser")
    form1 = soup1.select_one("form")
    action1 = form1.get("action") or r1.url
    if not action1.startswith("http"):
        action1 = urllib.parse.urljoin(r1.url, action1)
    data1 = {inp.get("name"): inp.get("value", "") for inp in form1.select("input") if inp.get("name")}

    print("[2] POST", action1)
    r2 = session.post(action1, data=data1, headers={"Referer": r1.url})
    soup2 = BeautifulSoup(r2.text, "html.parser")
    form2 = soup2.select_one("form")
    action2 = form2.get("action") or r2.url
    if not action2.startswith("http"):
        action2 = urllib.parse.urljoin(r2.url, action2)
    data2 = {inp.get("name"): inp.get("value", "") for inp in form2.select("input") if inp.get("name")}

    print("[3] POST", action2)
    r3 = session.post(action2, data=data2, headers={"Referer": r2.url})

    match_cookie = re.search(r"s_\d+\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", r3.text)
    match_go = re.search(r"https?://[^'\"\s]+/\?go=([^'\"\s]+)", r3.text)

    c_name, c_val = match_cookie.groups()
    go_param = match_go.group(1)
    base_domain = urllib.parse.urlsplit(r3.url).netloc
    go_url = f"https://{base_domain}/?go={go_param}"

    print(f"Cookie: {c_name}={c_val}")
    session.cookies.set(c_name, c_val, domain=base_domain)

    print("[4] GET go_url:", go_url)
    r4 = session.get(go_url, headers={"Referer": r3.url, "Cookie": f"{c_name}={c_val}"})
    print("r4 status:", r4.status_code)
    print("r4 text:\n", r4.text[:600])

if __name__ == "__main__":
    run_curl()
