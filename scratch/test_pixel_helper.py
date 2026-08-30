import asyncio
import os
import sys
import urllib.parse
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import moviesdrive_perf as perf

async def test_pixel_resolver():
    pixel_url = "https://pixel.hubcloud.cx/?id=1864755802c7d1d04e59e6dc50dd3b3d5ae64077cf05f161d27ce082843d8a75ab92760b2299e65d3a61b4cf814c7571f68b9c50f0aa69e6bec8d2a7f5ed33c5e49671344a6f9afc79c2a51e53d299964a4c036039d7c0d779f787c3094f2006::280060123eb71affc960fb203d26394d"
    referer = "https://gamerxyt.com/"
    
    client = await perf.get_client()
    r = await client.get(pixel_url, headers={"Referer": referer}, follow_redirects=True)
    final_url_str = str(r.url)
    print("Final URL:", final_url_str)
    
    parsed = urllib.parse.urlsplit(final_url_str)
    params = urllib.parse.parse_qs(parsed.query)
    if "link" in params and params["link"][0].startswith("http"):
        print("Successfully extracted link from URL params:", params["link"][0][:80], "...")
        
    await perf.aclose_client()

if __name__ == "__main__":
    asyncio.run(test_pixel_resolver())
