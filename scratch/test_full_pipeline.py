import asyncio
import os
import sys
import re
import urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx
from bs4 import BeautifulSoup
import uhdmovies_perf as perf

async def test_full_resolution():
    client = await perf.get_client()
    
    test_links = [
        # Somebody 2025 1080p H.264 (6.47 GB)
        'https://cloud.unblockedgames.world/?sid=a3Y4azk3STZ5RVphb1c0d0pkeDllaWVjc3NTd1dyeHJZSlNRUkszSnJFSGphampKSXNSZWwrcG5LYTJEYkE2UkZIZjJJc3VDQ1hhdW9jVTJmTTFzU29PMlFKZ0MzTmhvSC9NWEh6a0Z2T2RqWmdlSk9pYmVnRVpFYzFiVlNIcFB4NDY5NFJQUjZBR0Mvd1Q5QXp0UmJ5dmNpME9HajlVWlRReWRybnJNYWJwdHhxZ1NyVVM2TEZjQ3F1VThzSkR5NExYT3huY1A1MUltOTBJY29wcnA1MUVQSVJ3SVp1NWFiSERpTDNsL2lDb3ZOY2p0OFd2MUlNcHhHaGpQNGJmSg==',
        # Somebody 2025 1080p HEVC (3.95 GB)
        'https://cloud.unblockedgames.world/?sid=a3Y4azk3STZ5RVphb1c0d0pkeDllaWVjc3NTd1dyeHJZSlNRUkszSnJFSGphampKSXNSZWwrcG5LYTJEYkE2UkZIZjJJc3VDQ1hhdW9jVTJmTTFzU29PMlFKZ0MzTmhvSC9NWEh6a0Z2T2NIWXNlRVkyNmxrWWFjS1JjcE90cTd6aTF3ZFNCUFl6dSt2eHZkb01jdHNYRitsdXdZdkpVaWVXY2M2cWoxZ3dzQjJYaU5GemFkRGxZTTloeGltbnVjVmhBZWdnM2VFMGFUbHZjbEdzLzdSRGFRaG9PaGZRRHdFZEJBcFNNSFV2Ti96ZERMVFhjdGdHbTZsQ3IrUmVjTg=='
    ]
    
    for link in test_links:
        print("\n" + "="*50)
        print("Resolving link:", link[:60] + "...")
        
        # Step 1: GET landing
        r1 = await client.get(link)
        soup1 = BeautifulSoup(r1.text, "html.parser")
        form1 = soup1.select_one("form")
        action1 = form1.get("action") or link
        data1 = {inp.get("name"): inp.get("value", "") for inp in form1.select("input") if inp.get("name")}
        
        # Step 2: POST form 1
        r2 = await client.post(action1, data=data1, headers={"Referer": link})
        soup2 = BeautifulSoup(r2.text, "html.parser")
        form2 = soup2.select_one("form")
        action2 = form2.get("action") or str(r2.url)
        data2 = {inp.get("name"): inp.get("value", "") for inp in form2.select("input") if inp.get("name")}
        
        # Step 3: POST form 2
        r3 = await client.post(action2, data=data2, headers={"Referer": str(r2.url)})
        match_cookie = re.search(r"s_\d+\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", r3.text)
        match_go = re.search(r"https?://[^'\"\s]+/\?go=([^'\"\s]+)", r3.text)
        
        c_name, c_val = match_cookie.groups()
        go_param = match_go.group(1)
        base_domain = urllib.parse.urlsplit(str(r3.url)).netloc
        go_url = f"https://{base_domain}/?go={go_param}"
        client.cookies.set(c_name, c_val, domain=base_domain)
        
        # Step 4: GET go_url
        r4 = await client.get(go_url, headers={"Referer": str(r3.url)})
        meta_refresh = re.search(r'content=["\']\d+;\s*url=([^"\']+)["\']', r4.text, re.I)
        target_url = meta_refresh.group(1)
        print("Target URL from unblockedgames:", target_url)
        
        # Step 5: Follow target url -> driveseed
        r5 = await client.get(target_url, headers={"Referer": str(r4.url)})
        file_match = re.search(r'window\.location\.replace\(["\']([^"\']+)["\']\)', r5.text)
        driveseed_file_url = urllib.parse.urljoin(str(r5.url), file_match.group(1)) if file_match else str(r5.url)
        print("Driveseed File Page:", driveseed_file_url)
        
        # Step 6: On driveseed file page, extract /zfile/ (Resume Cloud) or instant download
        r6 = await client.get(driveseed_file_url, headers={"Referer": str(r5.url)})
        soup6 = BeautifulSoup(r6.text, "html.parser")
        
        zfile_url = None
        for a in soup6.select("a[href]"):
            href = a.get("href")
            btn_text = a.get_text(strip=True).lower()
            if "/zfile/" in href or "resume cloud" in btn_text:
                zfile_url = urllib.parse.urljoin(str(r6.url), href)
                break
                
        if zfile_url:
            print("Found zfile URL:", zfile_url)
            r_z = await client.get(zfile_url, headers={"Referer": driveseed_file_url})
            soup_z = BeautifulSoup(r_z.text, "html.parser")
            direct_video_url = None
            for a in soup_z.select("a[href]"):
                h = a.get("href")
                t = a.get_text(strip=True).lower()
                if "cloud resume download" in t or "workers.dev" in h or ".mkv" in h or ".mp4" in h or "googleusercontent" in h:
                    direct_video_url = h
                    break
            print(">>> FINAL DIRECT STREAM URL:", direct_video_url)
            
            # Check video stream response
            r_stream = await client.get(direct_video_url, headers={"Range": "bytes=0-100"})
            print(f"Stream verification: Status={r_stream.status_code}, Content-Type={r_stream.headers.get('content-type')}, Length={len(r_stream.content)}")

asyncio.run(test_full_resolution())
