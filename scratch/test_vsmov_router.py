import sys
import os
sys.path.insert(0, os.path.abspath("."))
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.stdout.reconfigure(encoding='utf-8')

from vsmov_router import vsmov_router


app = FastAPI()
app.include_router(vsmov_router)

client = TestClient(app)

def test_vsmov_addon():
    print("Testing VSMov Stremio Addon endpoints...\n")

    # 1. Manifest
    res = client.get("/vsmov/manifest.json")
    assert res.status_code == 200, f"Manifest failed: {res.status_code}"
    manifest = res.json()
    assert manifest["id"] == "com.stremio.vsmov.addon"
    print("✅ Manifest test passed")

    # 2. Catalog
    res = client.get("/vsmov/catalog/movie/vsmov_phim_moi.json")
    assert res.status_code == 200, f"Catalog failed: {res.status_code}"
    data = res.json()
    metas = data.get("metas", [])
    assert len(metas) > 0, "Catalog returned empty metas"
    first_item = metas[0]
    print(f"✅ Catalog test passed: Got {len(metas)} items. First: {first_item['name']} ({first_item['id']})")

    first_id = first_item["id"]

    # 3. Search
    res = client.get("/vsmov/catalog/movie/vsmov_phim_moi.json?search=nguu")
    assert res.status_code == 200, f"Search failed: {res.status_code}"
    search_data = res.json()
    search_metas = search_data.get("metas", [])
    print(f"✅ Search test passed: Got {len(search_metas)} items for 'nguu'")

    # 4. Meta
    res = client.get(f"/vsmov/meta/movie/{first_id}.json")
    assert res.status_code == 200, f"Meta failed: {res.status_code}"
    meta_data = res.json()
    meta = meta_data.get("meta", {})
    assert meta.get("name"), "Meta returned no name"
    print(f"✅ Meta test passed for {first_id}: {meta['name']}")

    # 5. Stream
    res = client.get(f"/vsmov/stream/movie/{first_id}.json")
    assert res.status_code == 200, f"Stream failed: {res.status_code}"
    stream_data = res.json()
    streams = stream_data.get("streams", [])
    assert len(streams) > 0, "Stream returned no streams"
    print(f"✅ Stream test passed: Got {len(streams)} streams.")
    for s in streams:
        print(f"   - {s.get('name')}: {s.get('url') or s.get('externalUrl')}")

    print("\n🎉 ALL VSMOV UNIT TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_vsmov_addon()
