import sys, os
sys.path.insert(0, os.path.abspath("."))
from fastapi.testclient import TestClient
from addon import app

client = TestClient(app)

from dashboard_router import generate_session_token

def test_dashboard():
    print("Testing /dashboard UI...")
    token = generate_session_token("admin")
    client.cookies.set("dashboard_session", token)
    res = client.get("/dashboard")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert "Addon Studio" in res.text

    print("Testing /api/system/status...")
    res = client.get("/api/system/status")
    assert res.status_code == 200
    data = res.json()
    print("Status response online:", data["status"])
    assert data["status"] == "online"

    print("Testing /api/system/addons...")
    res = client.get("/api/system/addons")
    assert res.status_code == 200
    addons = res.json()["addons"]
    print(f"Loaded {len(addons)} addons:")
    for a in addons:
        print(f" - {a['name'].encode('ascii', 'ignore').decode()} -> {a['manifests']['lan']}")
    assert len(addons) >= 8

    print("Testing /api/system/logs...")
    res = client.get("/api/system/logs")
    assert res.status_code == 200

    print("Testing /api/search with all sources...")
    res = client.get("/api/search?q=avatar&source=all")
    assert res.status_code == 200
    search_data = res.json()
    print(f"Universal Search found {search_data.get('total', 0)} results across sources.")

    print("Testing /api/search with specific sources...")
    for s in ["nguonc", "vsmov", "moviesdrive", "hdhub4u", "topxx"]:
        r = client.get(f"/api/search?q=spider&source={s}")
        assert r.status_code == 200
        print(f" - Source [{s}]: {r.json().get('total', 0)} results")

    print("Testing /api/config/update (toggle auto_vietsub & offset)...")
    res = client.post("/api/config/update", json={"auto_vietsub": True, "subtitle_offset": 1.5})
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["success"] is True
    assert res_data["services"]["auto_vietsub"] is True
    assert res_data["services"]["subtitle_offset"] == 1.5

    # Toggle it off
    res = client.post("/api/config/update", json={"auto_vietsub": False})
    assert res.status_code == 200
    assert res.json()["services"]["auto_vietsub"] is False

    print("All Dashboard tests passed successfully!")

if __name__ == "__main__":
    test_dashboard()
