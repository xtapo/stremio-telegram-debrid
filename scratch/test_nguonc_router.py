import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nguonc_router import nguonc_router

app = FastAPI()
app.include_router(nguonc_router, prefix="/nguonc")
app.include_router(nguonc_router)

client = TestClient(app)

def test_manifest():
    res = client.get("/nguonc/manifest.json")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "com.stremio.nguonc.phim"
    assert len(data["catalogs"]) >= 4
    print("✅ Manifest test passed")

def test_catalog():
    res = client.get("/nguonc/catalog/movie/nguonc_phim_le.json")
    assert res.status_code == 200
    data = res.json()
    assert "metas" in data
    assert len(data["metas"]) > 0
    first = data["metas"][0]
    print(f"✅ Catalog test passed: Got {len(data['metas'])} items. First: {first['name']} ({first['id']})")
    return first["id"]

def test_search():
    res = client.get("/nguonc/catalog/movie/nguonc_phim_le/search=Sugar.json")
    assert res.status_code == 200
    data = res.json()
    assert "metas" in data
    print(f"✅ Search test passed: Got {len(data['metas'])} items for 'Search'")

def test_meta(meta_id):
    res = client.get(f"/nguonc/meta/movie/{meta_id}.json")
    assert res.status_code == 200
    data = res.json()
    assert "meta" in data
    meta = data["meta"]
    assert meta["name"]
    print(f"✅ Meta test passed for {meta_id}: {meta['name']}")

def test_stream(meta_id):
    res = client.get(f"/nguonc/stream/movie/{meta_id}.json")
    assert res.status_code == 200
    data = res.json()
    assert "streams" in data
    streams = data["streams"]
    print(f"✅ Stream test passed: Got {len(streams)} streams.")
    for s in streams:
        print(f"   - {s['name']}: {s.get('url') or s.get('externalUrl')}")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    print("Testing NguonC Stremio Addon endpoints...")
    test_manifest()
    first_id = test_catalog()
    test_search()
    test_meta(first_id)
    test_stream(first_id)
    print("\n🎉 ALL UNIT TESTS PASSED SUCCESSFULLY!")
