import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import asyncio
import httpx
from fastapi.testclient import TestClient
from addon import app

client = TestClient(app)

def test_iptv_integration():
    print("=== 1. Testing /iptv/manifest.json ===")
    res = client.get("/iptv/manifest.json")
    print("Status:", res.status_code)
    assert res.status_code == 200
    manifest = res.json()
    print("Manifest ID:", manifest.get("id"))
    print("Manifest Name:", manifest.get("name"))
    print("Catalogs:", len(manifest.get("catalogs", [])))
    assert manifest.get("id") == "com.stremio.iptv.org"

    print("\n=== 2. Testing /iptv/catalog/tv/iptv_channels.json (Default VN) ===")
    res = client.get("/iptv/catalog/tv/iptv_channels.json")
    print("Status:", res.status_code)
    assert res.status_code == 200
    catalog = res.json()
    metas = catalog.get("metas", [])
    print(f"Loaded {len(metas)} VN channels.")
    assert len(metas) > 0
    sample_ch = metas[0]
    print(f"Sample channel: {sample_ch['name']} (ID: {sample_ch['id']})")

    print("\n=== 3. Testing /iptv/catalog/tv/iptv_channels/genre=🇺🇸 United States [US].json ===")
    res = client.get("/iptv/catalog/tv/iptv_channels/genre=%F0%9F%87%BA%F0%9F%87%B8%20United%20States%20%5BUS%5D.json")
    print("Status:", res.status_code)
    assert res.status_code == 200
    us_catalog = res.json()
    us_metas = us_catalog.get("metas", [])
    print(f"Loaded {len(us_metas)} US channels.")
    assert len(us_metas) > 0

    print("\n=== 4. Testing /iptv/meta/tv/{id}.json ===")
    ch_id = sample_ch["id"]
    res = client.get(f"/iptv/meta/tv/{ch_id}.json")
    print("Status:", res.status_code)
    assert res.status_code == 200
    meta_data = res.json().get("meta", {})
    print("Meta Name:", meta_data.get("name"))
    print("Genres:", meta_data.get("genres"))
    assert meta_data.get("id") == ch_id

    print("\n=== 5. Testing /iptv/stream/tv/{id}.json ===")
    res = client.get(f"/iptv/stream/tv/{ch_id}.json")
    print("Status:", res.status_code)
    assert res.status_code == 200
    streams_data = res.json().get("streams", [])
    print(f"Resolved {len(streams_data)} stream(s).")
    assert len(streams_data) > 0
    print("Stream URL:", streams_data[0].get("url"))

    print("\n=== 6. Testing /iptv/tv Web Player UI ===")
    res = client.get("/iptv/tv")
    print("Status:", res.status_code)
    assert res.status_code == 200
    assert "IPTV ORG GLOBAL" in res.text

    print("\n=== 7. Testing /iptv/api/countries & channels ===")
    res = client.get("/iptv/api/countries")
    assert res.status_code == 200
    print("Countries count:", len(res.json().get("countries", [])))

    res = client.get("/iptv/api/channels?country=jp")
    assert res.status_code == 200
    jp_channels = res.json().get("channels", [])
    print("JP channels count:", len(jp_channels))
    assert len(jp_channels) > 0

    print("\n✅ ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_iptv_integration()
