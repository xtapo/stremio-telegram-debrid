import asyncio
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from addon import app

client = TestClient(app)

def test_tvrun_integration():
    print("=== 1. Testing /tvrun/manifest.json ===")
    res = client.get("/tvrun/manifest.json")
    print(f"Status: {res.status_code}")
    assert res.status_code == 200
    manifest = res.json()
    assert manifest.get("id") == "com.stremio.tvrun.online"
    assert manifest.get("types") == ["tv"]
    print("Manifest OK:", manifest.get("name"))

    print("\n=== 2. Testing /tvrun/catalog/tv/tvrun_channels.json (Default VN) ===")
    res = client.get("/tvrun/catalog/tv/tvrun_channels.json")
    print(f"Status: {res.status_code}")
    assert res.status_code == 200
    data = res.json()
    metas = data.get("metas", [])
    print(f"Loaded {len(metas)} channels for default (VN)")
    assert len(metas) > 0
    first_ch = metas[0]
    ch_id = first_ch.get("id")
    print(f"First Channel: {first_ch.get('name')} (ID: {ch_id})")

    print("\n=== 3. Testing /tvrun/catalog/tv/tvrun_channels/genre=🌐 Free-TV Global [FREETV].json ===")
    res = client.get("/tvrun/catalog/tv/tvrun_channels/genre=%F0%9F%8C%90%20Free-TV%20Global%20%5BFREETV%5D.json")
    print(f"Status: {res.status_code}")
    assert res.status_code == 200
    freetv_metas = res.json().get("metas", [])
    print(f"Loaded {len(freetv_metas)} Free-TV Global channels")
    assert len(freetv_metas) > 0

    print("\n=== 4. Testing /tvrun/catalog/tv/tvrun_channels/genre=⭐ TVRun Verified [FEATURED].json ===")
    res = client.get("/tvrun/catalog/tv/tvrun_channels/genre=%E2%AD%90%20TVRun%20Verified%20%5BFEATURED%5D.json")
    print(f"Status: {res.status_code}")
    assert res.status_code == 200
    featured_metas = res.json().get("metas", [])
    print(f"Loaded {len(featured_metas)} Featured channels (e.g. {featured_metas[0].get('name')})")
    assert len(featured_metas) > 0
    featured_id = featured_metas[0].get("id")

    print(f"\n=== 5. Testing /tvrun/meta/tv/{featured_id}.json ===")
    res = client.get(f"/tvrun/meta/tv/{featured_id}.json")
    print(f"Status: {res.status_code}")
    assert res.status_code == 200
    meta = res.json().get("meta", {})
    print("Meta Name:", meta.get("name"))
    print("Meta Genres:", meta.get("genres"))
    assert meta.get("id") == featured_id

    print(f"\n=== 6. Testing /tvrun/stream/tv/{featured_id}.json ===")
    res = client.get(f"/tvrun/stream/tv/{featured_id}.json")
    print(f"Status: {res.status_code}")
    assert res.status_code == 200
    streams = res.json().get("streams", [])
    print(f"Found {len(streams)} streams")
    assert len(streams) > 0
    print("Stream URL:", streams[0].get("url"))

    print("\n=== 7. Testing /tvrun/playlist.m3u (M3U Export) ===")
    res = client.get("/tvrun/playlist.m3u?source=featured")
    print(f"Status: {res.status_code}")
    assert res.status_code == 200
    assert "#EXTM3U" in res.text
    print("M3U Export OK, lines:", len(res.text.splitlines()))

    print("\n=== 8. Testing /tvrun/tv Web Player UI ===")
    res = client.get("/tvrun/tv")
    print(f"Status: {res.status_code}")
    assert res.status_code == 200
    assert "TVRUN ONLINE" in res.text
    print("Web Player UI OK")

    print("\n=== 9. Testing /tvrun/api/countries & /tvrun/api/channels ===")
    res = client.get("/tvrun/api/countries")
    assert res.status_code == 200
    c_data = res.json()
    print("Special sources count:", len(c_data.get("special", [])))
    print("Popular countries count:", len(c_data.get("popular", [])))

    res = client.get("/tvrun/api/channels?source=vn")
    assert res.status_code == 200
    ch_data = res.json()
    print("VN channels count:", ch_data.get("total", 0))

    print("\n=== 10. Testing Dashboard Integration for TVRun ===")
    res = client.get("/api/system/addons")
    assert res.status_code == 200
    addons = res.json().get("addons", [])
    tvrun_addon = next((a for a in addons if a.get("id") == "tvrun"), None)
    assert tvrun_addon is not None
    print("Dashboard Addon Found:", tvrun_addon.get("name"))
    print("Player URL:", tvrun_addon.get("player_url"))
    print("Manifests:", tvrun_addon.get("manifests"))

    res = client.post("/api/config/update", json={"enable_source_tvrun": True, "enable_board_tvrun": True})
    assert res.status_code == 200
    data = res.json()
    assert data.get("sources", {}).get("tvrun") is True
    assert data.get("board", {}).get("tvrun") is True
    print("Config update toggle OK")

    res = client.post("/api/cache/clear")
    assert res.status_code == 200
    cleared = res.json().get("cleared", [])
    assert any("TVRun" in c for c in cleared)
    print("Cache Clear OK:", cleared)

    print("\n🎉 ALL TVRUN INTEGRATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_tvrun_integration()
