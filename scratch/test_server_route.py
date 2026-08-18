import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from addon import app

client = TestClient(app)

# 1. Test Manifest
r_manifest = client.get("/hdtoday/manifest.json")
print("Manifest status:", r_manifest.status_code)
assert r_manifest.status_code == 200

# 2. Test Stream Proxy route with empty url (should return 422/400 Validation/Missing url parameter, NOT 404)
r_proxy = client.get("/hdtoday/stream_proxy")
print("Proxy empty url status:", r_proxy.status_code, r_proxy.json())
assert r_proxy.status_code in [400, 422]

# 3. Test Full Stream extraction on Hotel Desire (movie from user terminal log)
r_stream = client.get("/hdtoday/stream/movie/hdtoday:movie:hotel-desire-Xr6YI9kJ0QP.json")
print("Stream status:", r_stream.status_code)
streams = r_stream.json().get("streams", [])
print("Extracted streams count:", len(streams))
for s in streams:
    print(" - Stream:", s.get("name"), "->", s.get("url") or s.get("externalUrl"))

# 4. Test Proxy on the extracted primary stream
primary = next((s for s in streams if "/hdtoday/stream_proxy" in s.get("url", "")), None)
assert primary is not None, "Expected primary proxy stream"
print("\nFetching primary stream through proxy:")
r_play = client.get(primary["url"])
print("Master m3u8 proxy status:", r_play.status_code)
print("Content-Type:", r_play.headers.get("content-type"))
assert r_play.status_code == 200
assert "#EXTM3U" in r_play.text
print("Master playlist sample:\n", r_play.text[:400])

# 5. Extract a child stream URL from master playlist and fetch it through proxy
child_url = None
for line in r_play.text.splitlines():
    if "/hdtoday/stream_proxy" in line:
        child_url = line.strip()
        break

assert child_url is not None
print("\nFetching child playlist through proxy:", child_url[:100])
r_child = client.get(child_url)
print("Child playlist status:", r_child.status_code)
assert r_child.status_code == 200
print("Child playlist sample:\n", r_child.text[:400])

# 6. Extract key or TS chunk from child playlist and fetch it
ts_url = None
for line in r_child.text.splitlines():
    if "/hdtoday/stream_proxy" in line:
        ts_url = line.strip()
        break

assert ts_url is not None
print("\nFetching media chunk/key through proxy:", ts_url[:100])
r_ts = client.get(ts_url)
print("Chunk status:", r_ts.status_code, "Bytes:", len(r_ts.content))
assert r_ts.status_code == 200

print("\n🎉 ALL TESTS PASSED! VIDEO PLAYBACK WORKS 100%!")
