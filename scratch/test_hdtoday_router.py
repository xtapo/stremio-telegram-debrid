import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
from starlette.requests import Request
from hdtoday_router import (
    get_hdtoday_manifest,
    hdtoday_catalog_handler,
    hdtoday_meta_handler,
    hdtoday_stream_handler,
    hdtoday_stream_proxy
)

async def run_tests():
    print("1. Testing Manifest...")
    manifest = get_hdtoday_manifest()
    assert manifest["id"] == "com.stremio.hdtoday.addon"
    print("Manifest OK! Catalogs count:", len(manifest["catalogs"]))

    print("\n2. Testing Stream Handler...")
    scope = {"type": "http", "base_url": "http://localhost:7860", "headers": []}
    req = Request(scope)
    stream_res = await hdtoday_stream_handler(req, "movie", "hdtoday:movie:avatar-7yeqHJL09WY")
    streams = stream_res.get("streams", [])
    assert len(streams) > 0

    proxy_stream = next((s for s in streams if "/hdtoday/stream_proxy" in s.get("url", "")), None)
    assert proxy_stream is not None, "Expected proxy stream"
    print("Found Proxy Stream:", proxy_stream["name"])

    print("\n3. Testing Stream Proxy Endpoint...")
    # Extract url and referer from query string
    import urllib.parse
    parsed = urllib.parse.urlparse(proxy_stream["url"])
    qs = urllib.parse.parse_qs(parsed.query)
    target_m3u8 = qs["url"][0]
    target_ref = qs["referer"][0]

    proxy_req = Request({
        "type": "http",
        "base_url": "http://localhost:7860",
        "headers": [(b"user-agent", b"Mozilla/5.0"), (b"accept", b"*/*")]
    })
    resp = await hdtoday_stream_proxy(proxy_req, url=target_m3u8, referer=target_ref)
    print("Proxy Response Status:", resp.status_code)
    print("Proxy Response Content-Type:", resp.headers.get("content-type"))
    body_text = resp.body.decode("utf-8")
    assert "#EXTM3U" in body_text
    assert "/hdtoday/stream_proxy" in body_text
    print("Proxy successfully rewrote M3U8 URLs! Preview:\n", body_text[:400])

    print("\nALL VERIFICATIONS PASSED!")

if __name__ == "__main__":
    asyncio.run(run_tests())
