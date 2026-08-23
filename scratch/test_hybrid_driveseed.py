import asyncio
import os
import sys
import re
import urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx
from bs4 import BeautifulSoup
import uhdmovies_perf as perf

async def resolve_driveseed_file(driveseed_file_url: str, referer: str = "") -> str:
    client = await perf.get_client()
    r6 = await client.get(driveseed_file_url, headers={"Referer": referer}, timeout=20.0)
    soup6 = BeautifulSoup(r6.text, "html.parser")
    
    zfile_url = None
    instant_download_url = None
    
    for a in soup6.select("a[href]"):
        href = a.get("href")
        btn_text = a.get_text(strip=True).lower()
        if not href or "login" in href.lower() or href.startswith("#"):
            continue
        if "/zfile/" in href or "resume cloud" in btn_text:
            zfile_url = urllib.parse.urljoin(str(r6.url), href)
        if "instant download" in btn_text or "direct download" in btn_text or "video-gen" in href:
            instant_download_url = urllib.parse.urljoin(str(r6.url), href)

    # 1. Try /zfile/ (Resume Cloud)
    if zfile_url:
        try:
            r_z = await client.get(zfile_url, headers={"Referer": driveseed_file_url}, timeout=15.0)
            soup_z = BeautifulSoup(r_z.text, "html.parser")
            for a in soup_z.select("a[href]"):
                h = a.get("href")
                t = a.get_text(strip=True).lower()
                if (
                    "cloud resume download" in t
                    or "workers.dev" in h
                    or any(h.endswith(ext) or ext in h for ext in (".mkv", ".mp4", ".m4v"))
                    or "googleusercontent" in h
                ):
                    return h
        except Exception as e:
            print("zfile fetch error:", e)

    # 2. Try Instant Download / video-gen / video-seed
    if instant_download_url:
        try:
            # First try GET with follow_redirects=False
            r_inst = await client.get(instant_download_url, headers={"Referer": driveseed_file_url}, timeout=15.0)
            loc = r_inst.headers.get("location", "")
            if not loc and r_inst.status_code in (301, 302, 303, 307, 308):
                loc = r_inst.headers.get("Location", "")
                
            if loc:
                if "url=" in loc:
                    parsed_loc = urllib.parse.urlsplit(loc)
                    q = urllib.parse.parse_qs(parsed_loc.query)
                    real_u = q.get("url", [None])[0]
                    if real_u and real_u.startswith("http"):
                        return real_u
                if "googleusercontent.com" in loc or "workers.dev" in loc or "r2.dev" in loc:
                    return loc

            # If HTML returned, search for googleusercontent or workers.dev in HTML/JS
            text = r_inst.text
            match_g = re.search(r'(https://video-downloads\.googleusercontent\.com/[^\s\'"<>]+)', text)
            if match_g:
                return match_g.group(1)
                
            match_w = re.search(r'(https://[^\s\'"<>]+workers\.dev/[^\s\'"<>]+)', text)
            if match_w:
                return match_w.group(1)
        except Exception as e:
            print("instant_download error:", e)
            
    return None

async def test():
    urls = [
        # Supergirl 2026 (fails on zfile, succeeds on instant download)
        "https://driveseed.org/file/vMHFjZm67Ve6pRIHLnpZ",
        # Somebody 2025 (succeeds on zfile)
        "https://driveseed.org/file/pBvUumcCBl",
    ]
    for u in urls:
        print("\nTesting:", u)
        res = await resolve_driveseed_file(u)
        print(">>> RESULT:", res)
        if res:
            client = await perf.get_client()
            r_check = await client.get(res, headers={"Range": "bytes=0-100"})
            print(f"Stream verification: Status={r_check.status_code}, Length={len(r_check.content)}")

asyncio.run(test())
