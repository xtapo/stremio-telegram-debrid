import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import unittest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from hhpanda_router import hhpanda_router

sys.stdout.reconfigure(encoding='utf-8')

app = FastAPI()
app.include_router(hhpanda_router, prefix="/hhpanda")
client = TestClient(app)

class TestHHPandaRouter(unittest.TestCase):
    def test_manifest(self):
        res = client.get("/hhpanda/manifest.json")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["id"], "com.stremio.hhpanda.addon")
        self.assertIn("HHPanda", data["name"])
        print("✅ Manifest test passed")

    def test_catalog_latest(self):
        res = client.get("/hhpanda/catalog/series/hhpanda_moi_cap_nhat.json")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("metas", data)
        self.assertGreater(len(data["metas"]), 0)
        first_item = data["metas"][0]
        self.assertTrue(first_item["id"].startswith("hhpanda:"))
        print(f"✅ Catalog latest test passed ({len(data['metas'])} items, first: {first_item['name']})")

    def test_catalog_genre(self):
        res = client.get("/hhpanda/catalog/series/hhpanda_the_loai.json?genre=Tu%20Ti%C3%AAn")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("metas", data)
        self.assertGreater(len(data["metas"]), 0)
        print(f"✅ Catalog genre test passed ({len(data['metas'])} items)")

    def test_catalog_search(self):
        res = client.get("/hhpanda/catalog/series/hhpanda_moi_cap_nhat.json?search=Ti%C3%AAn%20Ngh%E1%BB%8Bch")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("metas", data)
        self.assertGreater(len(data["metas"]), 0)
        print(f"✅ Catalog search test passed ({len(data['metas'])} search results)")

    def test_meta(self):
        res = client.get("/hhpanda/meta/series/hhpanda:tien-nghich.json")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("meta", data)
        meta = data["meta"]
        self.assertEqual(meta["id"], "hhpanda:tien-nghich")
        self.assertIn("videos", meta)
        self.assertGreater(len(meta["videos"]), 0)
        print(f"✅ Meta test passed (Title: {meta['name']}, Episodes: {len(meta['videos'])})")

    def test_stream(self):
        res_meta = client.get("/hhpanda/meta/series/hhpanda:tien-nghich.json")
        meta = res_meta.json()["meta"]
        first_video = meta["videos"][0]
        video_id = first_video["id"]
        
        res_stream = client.get(f"/hhpanda/stream/series/{video_id}.json")
        self.assertEqual(res_stream.status_code, 200)
        sdata = res_stream.json()
        self.assertIn("streams", sdata)
        self.assertGreater(len(sdata["streams"]), 0)
        print(f"✅ Stream test passed ({len(sdata['streams'])} streams for {video_id})")

    def test_player_proxy(self):
        res = client.get("/hhpanda/player_proxy?src=https%3A%2F%2Fstreamfree.vip%2Fembed%2Fv%2FVt6tBD37")
        self.assertEqual(res.status_code, 200)
        self.assertTrue("<base href=" in res.text or "<iframe" in res.text or "<div" in res.text)
        print("✅ Player proxy test passed")

if __name__ == "__main__":
    unittest.main()
