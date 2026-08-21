import sys
import os
sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')

# Import FastAPI app
from addon import app
from fastapi.testclient import TestClient

client = TestClient(app)

print("=== 1. Testing /film4k/manifest.json ===")
res = client.get("/film4k/manifest.json")
print("Status:", res.status_code)
manifest = res.json()
print("ID:", manifest.get("id"))
print("Name:", manifest.get("name"))
print("Catalogs:", [c.get("name") for c in manifest.get("catalogs", [])])
assert res.status_code == 200
assert manifest.get("id") == "com.stremio.film4k.tv"

print("\n=== 2. Testing /film4k/catalog/tv/film4k_tv_channels.json ===")
res = client.get("/film4k/catalog/tv/film4k_tv_channels.json")
print("Status:", res.status_code)
cat_data = res.json()
metas = cat_data.get("metas", [])
print(f"Total TV channels returned: {len(metas)}")
assert res.status_code == 200
assert len(metas) > 50
print("Sample channels:", [m.get("name") for m in metas[:5]])

print("\n=== 3. Testing /film4k/catalog/tv/film4k_tv_channels/genre=VTV.json ===")
res = client.get("/film4k/catalog/tv/film4k_tv_channels/genre=VTV.json")
print("Status:", res.status_code)
vtv_metas = res.json().get("metas", [])
print(f"VTV channels: {len(vtv_metas)} -> {[m.get('name') for m in vtv_metas]}")
assert res.status_code == 200
assert len(vtv_metas) > 0

print("\n=== 4. Testing /film4k/catalog/tv/film4k_tv_events.json ===")
res = client.get("/film4k/catalog/tv/film4k_tv_events.json")
print("Status:", res.status_code)
event_metas = res.json().get("metas", [])
print(f"Live Events: {len(event_metas)}")
if event_metas:
    print("Sample event:", event_metas[0].get("name"))
assert res.status_code == 200

print("\n=== 5. Testing /film4k/meta/tv/film4k:channel:vtv1-hd.json ===")
res = client.get("/film4k/meta/tv/film4k:channel:vtv1-hd.json")
print("Status:", res.status_code)
meta_data = res.json().get("meta", {})
print("Meta name:", meta_data.get("name"))
print("Meta genres:", meta_data.get("genres"))
assert res.status_code == 200
assert "vtv1" in meta_data.get("name", "").lower() or "vtv1" in meta_data.get("id", "").lower()

print("\n=== 6. Testing /film4k/stream/tv/film4k:channel:vtv1-hd.json ===")
res = client.get("/film4k/stream/tv/film4k:channel:vtv1-hd.json")
print("Status:", res.status_code)
stream_data = res.json()
streams = stream_data.get("streams", [])
print(f"Streams returned: {len(streams)}")
if streams:
    print("Stream title:", streams[0].get("title"))
    print("Stream URL:", streams[0].get("url")[:80] + "...")
assert res.status_code == 200
assert len(streams) > 0

print("\n=== 7. Testing /film4k/live/vtv1-hd.m3u8 (Redirector) ===")
res = client.get("/film4k/live/vtv1-hd.m3u8", follow_redirects=False)
print("Status:", res.status_code)
print("Location Header:", res.headers.get("location", "")[:80] + "...")
assert res.status_code == 302
assert "m3u8" in res.headers.get("location", "")

print("\n=== 8. Testing /film4k/playlist.m3u (IPTV M3U Playlist) ===")
res = client.get("/film4k/playlist.m3u")
print("Status:", res.status_code)
m3u_text = res.text
print("Playlist lines:", len(m3u_text.splitlines()))
print("Playlist header snippet:")
print("\n".join(m3u_text.splitlines()[:6]))
assert res.status_code == 200
assert "#EXTM3U" in m3u_text

print("\n=== 9. Testing /film4k/status ===")
res = client.get("/film4k/status")
print("Status:", res.status_code)
print("Data:", res.json())
assert res.status_code == 200
assert res.json().get("status") == "online"

print("\n=== 10. Testing /film4k/tv (Web TV Player) ===")
res = client.get("/film4k/tv")
print("Status:", res.status_code)
print("HTML length:", len(res.text))
assert res.status_code == 200
assert "Film4k Live TV" in res.text

print("\n=== 11. Testing /api/system/addons (Dashboard) ===")
res = client.get("/api/system/addons")
addons = res.json().get("addons", [])
film4k_addon = next((a for a in addons if a.get("id") == "film4k_tv"), None)
print("Found Film4k TV addon in dashboard:", bool(film4k_addon))
if film4k_addon:
    print("Name:", film4k_addon.get("name"))
    print("Manifests:", film4k_addon.get("manifests"))
    print("Playlist URL:", film4k_addon.get("playlist_url"))
assert film4k_addon is not None

print("\n✅ ALL TESTS PASSED SUCCESSFULLY!")
