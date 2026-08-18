import asyncio
import httpx
import urllib.parse

async def test_stremio_simulation():
    """Simulate exactly what Stremio does with the stream URLs"""
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(15.0, connect=6.0),
        follow_redirects=True,
    )
    
    base = "http://localhost:7860"
    
    # Get streams
    res = await client.get(f"{base}/ernax/stream/movie/tt0137523.json")
    data = res.json()
    streams = data.get("streams", [])
    
    # Find the 1080p stream  
    target = None
    for s in streams:
        if "1080" in s.get("name", ""):
            target = s
            break
    
    if not target:
        print("No 1080p stream found")
        await client.aclose()
        return
    
    url = target["url"]
    behavior_hints = target.get("behaviorHints", {})
    
    print("=== Stream object Stremio receives ===")
    print(f"URL: {url}")
    print(f"notWebReady: {behavior_hints.get('notWebReady')}")
    print(f"proxyHeaders: {behavior_hints.get('proxyHeaders')}")
    
    # Stremio with proxyHeaders AND notWebReady=False means:
    # Stremio will try to play the URL directly in its built-in player
    # It will NOT use proxyHeaders since notWebReady is False
    # (proxyHeaders only used when Stremio itself needs to fetch, 
    #  but for HLS, the video player fetches segments directly)
    
    # Key insight: When notWebReady=False, Stremio opens the URL in its
    # embedded web player. The web player makes direct HTTP requests.
    # Since the proxy rewrites URLs to localhost, this should work on same PC.
    
    # BUT: The issue could be with the Content-Type or CORS
    
    print("\n=== Testing proxy response headers ===")
    res2 = await client.get(url)
    print(f"Status: {res2.status_code}")
    print(f"Headers:")
    for k, v in res2.headers.items():
        print(f"  {k}: {v}")
    
    # Check if the M3U8 content is valid
    print(f"\nM3U8 valid: starts with #EXTM3U = {res2.text.startswith('#EXTM3U')}")
    
    # Check a segment
    import re
    lines = res2.text.splitlines()
    seg_url = None
    init_url = None
    for line in lines:
        stripped = line.strip()
        if 'URI="' in stripped:
            m = re.search(r'URI="([^"]+)"', stripped)
            if m:
                init_url = m.group(1)
        elif stripped.startswith("http") and not stripped.startswith("#"):
            if not seg_url:
                seg_url = stripped
    
    if init_url:
        print(f"\n=== Init segment response headers ===")
        res3 = await client.get(init_url)
        print(f"Status: {res3.status_code}")
        for k, v in res3.headers.items():
            print(f"  {k}: {v}")
        print(f"Content length: {len(res3.content)}")
        # Check first bytes for ftyp box (valid mp4)
        if len(res3.content) > 8:
            print(f"First 4 bytes (hex): {res3.content[:4].hex()}")
            print(f"MP4 ftyp box: {'ftyp' in res3.content[:12].decode('latin-1', errors='replace')}")
    
    if seg_url:
        print(f"\n=== First segment response headers ===")
        res4 = await client.get(seg_url)
        print(f"Status: {res4.status_code}")
        for k, v in res4.headers.items():
            print(f"  {k}: {v}")
        print(f"Content length: {len(res4.content)}")

    # Test with range request (Stremio may use these)
    if seg_url:
        print(f"\n=== Range request test ===")
        res5 = await client.get(seg_url, headers={"Range": "bytes=0-1023"})
        print(f"Status: {res5.status_code}")
        for k, v in res5.headers.items():
            print(f"  {k}: {v}")
    
    # Now test what happens if Stremio tries to fetch the URL directly 
    # (without going through our proxy - this is what happens with notWebReady=False)
    # When notWebReady=False, Stremio opens a web view that loads the URL
    # The web view's video player directly fetches the M3U8 and segments
    
    # The question is: does Stremio use HLS.js or native player?
    # If HLS.js, it should handle the proxy chain fine
    # If native, it depends on the OS
    
    # Check if there's a streaming endpoint issue
    print(f"\n=== Check: does proxy handle concurrent requests? ===")
    tasks = []
    test_urls = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("http") and not stripped.startswith("#"):
            test_urls.append(stripped)
            if len(test_urls) >= 3:
                break
    
    async def fetch_seg(url_to_fetch, idx):
        r = await client.get(url_to_fetch)
        return idx, r.status_code, len(r.content)
    
    results = await asyncio.gather(*[fetch_seg(u, i) for i, u in enumerate(test_urls)])
    for idx, status, length in results:
        print(f"  Segment {idx}: status={status}, length={length}")
    
    await client.aclose()

asyncio.run(test_stremio_simulation())
