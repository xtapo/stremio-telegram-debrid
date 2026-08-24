import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from nguonc_router import nguonc_router
import urllib.parse

app = FastAPI()
app.include_router(nguonc_router, prefix="/nguonc")
app.include_router(nguonc_router)

client = TestClient(app)

def test_nguonc_endpoints():
    print("--- 1. Testing Manifest ---")
    res = client.get("/nguonc/manifest.json")
    assert res.status_code == 200, f"Manifest failed: {res.status_code}"
    print("Manifest OK! Name:", res.json().get("name"))

    print("\n--- 2. Testing Catalog ---")
    res = client.get("/nguonc/catalog/movie/nguonc_phim_le.json")
    assert res.status_code == 200, f"Catalog failed: {res.status_code}"
    metas = res.json().get("metas", [])
    print(f"Catalog OK! Fetched {len(metas)} movies. Sample: {metas[0]['name']}")

    sample_id = metas[0]['id']  # e.g. nguonc:...
    print(f"\n--- 3. Testing Meta ({sample_id}) ---")
    res = client.get(f"/nguonc/meta/movie/{sample_id}.json")
    assert res.status_code == 200, f"Meta failed: {res.status_code}"
    print("Meta OK! Title:", res.json().get("meta", {}).get("name"))

    print(f"\n--- 4. Testing Stream ({sample_id}) ---")
    res = client.get(f"/nguonc/stream/movie/{sample_id}.json")
    assert res.status_code == 200, f"Stream endpoint failed: {res.status_code}"
    streams = res.json().get("streams", [])
    print(f"Stream OK! Fetched {len(streams)} streams.")
    for s in streams:
        print("  - Stream Name:", s.get("name"))
        print("    URL:", s.get("url") or s.get("externalUrl"))

    primary_stream = next((s for s in streams if "url" in s), None)
    assert primary_stream, "No primary proxy stream URL found in streams!"
    
    proxy_url = primary_stream["url"].replace("http://testserver", "")
    print(f"\n--- 5. Testing Stream Proxy Playlist ({proxy_url}) ---")
    proxy_res = client.get(proxy_url)
    assert proxy_res.status_code == 200, f"Proxy playlist failed: {proxy_res.status_code}"
    playlist = proxy_res.text
    assert "#EXTM3U" in playlist, "Playlist does not contain #EXTM3U!"
    print(f"Proxy Playlist OK! Length: {len(playlist)} bytes, {len(playlist.splitlines())} lines.")
    print("Playlist Preview:\n" + "\n".join(playlist.splitlines()[:8]))

    # Find first segment
    segment_url = None
    for line in playlist.splitlines():
        if "stream_proxy?url=" in line:
            segment_url = line.replace("http://testserver", "")
            break
            
    assert segment_url, "No segment URL found in rewritten playlist!"
    print(f"\n--- 6. Testing Stream Segment Fetch ({segment_url[:80]}...) ---")
    seg_res = client.get(segment_url)
    assert seg_res.status_code == 200, f"Segment fetch failed: {seg_res.status_code}"
    assert len(seg_res.content) > 1000, f"Segment size unexpectedly small: {len(seg_res.content)}"
    assert seg_res.content[0] == 0x47, f"Segment sync byte is not 0x47 (MPEG-TS): {seg_res.content[0]}"
    print(f"Segment Fetch OK! Size: {len(seg_res.content)} bytes, MPEG-TS sync byte: 0x47 (valid video chunk).")

    print("\n✅ ALL NGUONC TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    test_nguonc_endpoints()
