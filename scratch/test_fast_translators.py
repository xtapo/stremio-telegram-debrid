import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import time
import httpx
import urllib.parse
import re

async def test_methods():
    text = "Hello my prince! Where is the king? Kneel before the crown."
    
    # Method 1: Google Translate client=webapp
    print("Testing Method 1: Google WebApp...")
    try:
        url = "https://translate.google.com/translate_a/single"
        params = {"client": "gtx", "sl": "auto", "tl": "vi", "dt": "t", "q": text}
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with httpx.AsyncClient(headers=headers, timeout=5.0) as client:
            resp = await client.get(url, params=params)
            print("Method 1 status:", resp.status_code)
            if resp.status_code == 200:
                print("Method 1 result:", resp.json()[0][0][0])
    except Exception as e:
        print("Method 1 failed:", e)

    # Method 2: Google client=dict-chrome-ex
    print("\nTesting Method 2: Chrome Extension...")
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "dict-chrome-ex", "sl": "auto", "tl": "vi", "dt": "t", "q": text}
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        async with httpx.AsyncClient(headers=headers, timeout=5.0) as client:
            resp = await client.get(url, params=params)
            print("Method 2 status:", resp.status_code)
            if resp.status_code == 200:
                print("Method 2 result:", resp.json()[0][0][0])
    except Exception as e:
        print("Method 2 failed:", e)

    # Method 3: Lingva public API
    print("\nTesting Method 3: Lingva...")
    try:
        url = f"https://lingva.ml/api/v1/auto/vi/{urllib.parse.quote(text)}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            print("Method 3 status:", resp.status_code)
            if resp.status_code == 200:
                print("Method 3 result:", resp.json().get("translation"))
    except Exception as e:
        print("Method 3 failed:", e)

if __name__ == '__main__':
    asyncio.run(test_methods())
