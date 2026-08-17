import sys, os
sys.path.insert(0, os.path.abspath("."))
from fastapi.testclient import TestClient
from addon import app

client = TestClient(app)

def test_dashboard():
    print("Testing /dashboard UI...")
    res = client.get("/dashboard")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert "Trung Tâm Quản Lý Addon" in res.text

    print("Testing /api/system/status...")
    res = client.get("/api/system/status")
    assert res.status_code == 200
    data = res.json()
    print("Status response:", data)
    assert data["status"] == "online"

    print("Testing /api/system/addons...")
    res = client.get("/api/system/addons")
    assert res.status_code == 200
    addons = res.json()["addons"]
    print(f"Loaded {len(addons)} addons:")
    for a in addons:
        print(f" - {a['name'].encode('ascii', 'ignore').decode()} -> {a['manifests']['lan']}")
    assert len(addons) == 7

    print("Testing /api/system/logs...")
    res = client.get("/api/system/logs")
    assert res.status_code == 200

    print("All Dashboard tests passed successfully!")

if __name__ == "__main__":
    test_dashboard()
