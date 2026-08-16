import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from fastapi.testclient import TestClient
from addon import app

client = TestClient(app)

def test_full_addon_moviesdrive():
    # 1. Test MoviesDrive Manifest on main app
    resp = client.get("/moviesdrive/manifest.json")
    print("Main app /moviesdrive/manifest.json:", resp.status_code)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "com.stremio.moviesdrive.addon"
    print("Addon Name:", data["name"])

    # 2. Test Catalog
    resp = client.get("/moviesdrive/catalog/movie/moviesdrive_movies_4k.json")
    print("Main app /moviesdrive/catalog 4K status:", resp.status_code)
    assert resp.status_code == 200
    metas = resp.json().get("metas", [])
    print(f"Loaded {len(metas)} 4K metas from main app")

    # 3. Test Stream Resolution
    resp = client.get("/moviesdrive/stream/movie/moviesdrive:inception-2010.json")
    print("Main app /moviesdrive/stream status:", resp.status_code)
    assert resp.status_code == 200
    streams = resp.json().get("streams", [])
    print(f"Loaded {len(streams)} streams from main app")
    print("All integration tests passed successfully!")

if __name__ == "__main__":
    test_full_addon_moviesdrive()
