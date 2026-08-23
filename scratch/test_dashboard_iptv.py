import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from addon import app

client = TestClient(app)

def test_dashboard_iptv():
    print("=== 1. Testing /dashboard HTML ===")
    res = client.get("/dashboard")
    print("Status:", res.status_code)
    assert res.status_code == 200
    assert "Addon Studio" in res.text

    print("\n=== 2. Testing /api/system/addons ===")
    res = client.get("/api/system/addons")
    print("Status:", res.status_code)
    assert res.status_code == 200
    addons = res.json().get("addons", [])
    print(f"Total addons in dashboard: {len(addons)}")
    
    iptv_addon = next((a for a in addons if a.get("id") == "iptv"), None)
    assert iptv_addon is not None
    print("Found IPTV Addon:", iptv_addon.get("name"))
    print("Player URL:", iptv_addon.get("player_url"))
    print("Manifests:", iptv_addon.get("manifests"))

    print("\n=== 3. Testing /api/config/update toggle ===")
    res = client.post("/api/config/update", json={"enable_source_iptv": True, "enable_board_iptv": True})
    print("Status:", res.status_code)
    assert res.status_code == 200
    data = res.json()
    assert data.get("sources", {}).get("iptv") is True
    assert data.get("board", {}).get("iptv") is True

    print("\n=== 4. Testing /api/cache/clear ===")
    res = client.post("/api/cache/clear")
    print("Status:", res.status_code)
    assert res.status_code == 200
    cleared = res.json().get("cleared", [])
    print("Cleared caches:", cleared)
    assert any("IPTV" in c for c in cleared)

    print("\n🎉 DASHBOARD IPTV INTEGRATION TEST PASSED!")

if __name__ == "__main__":
    test_dashboard_iptv()
