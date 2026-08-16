import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
from fastapi.testclient import TestClient
from addon import app
from moviesdrive_router import CACHE
import urllib.parse

CACHE.clear()
client = TestClient(app)

def test_hotd_multi_season():
    # 1. Season 1 Episode 3
    print("\n=== Testing House of the Dragon Season 1 Episode 3 ===")
    s1e3_id = "moviesdrive:house-of-the-dragon-season-1-3:1:3"
    resp1 = client.get(f"/stream/series/{s1e3_id}.json")
    assert resp1.status_code == 200
    streams1 = resp1.json().get("streams", [])
    print(f"Got {len(streams1)} streams for S1E3:")
    assert len(streams1) > 0
    for s in streams1:
        print(f" - [{s['name']}] Title: {s['title'][:40]} => URL: {s['url'][:70]}...")
        
    p1 = urllib.parse.urlsplit(streams1[0]["url"])
    rel1 = p1.path + "?" + p1.query
    resp_v1 = client.get(rel1, headers={"Range": "bytes=0-1000"})
    print("S1E3 video status:", resp_v1.status_code)
    assert resp_v1.status_code in (200, 206)
    print(">>> Season 1 Episode 3: SUCCESS PLAYABLE! <<<")

    # 2. Season 2 Episode 2
    print("\n=== Testing House of the Dragon Season 2 Episode 2 ===")
    s2e2_id = "moviesdrive:house-of-the-dragon-season-1-3:2:2"
    resp2 = client.get(f"/stream/series/{s2e2_id}.json")
    assert resp2.status_code == 200
    streams2 = resp2.json().get("streams", [])
    print(f"Got {len(streams2)} streams for S2E2:")
    assert len(streams2) > 0
    for s in streams2:
        print(f" - [{s['name']}] Title: {s['title'][:40]} => URL: {s['url'][:70]}...")
        
    p2 = urllib.parse.urlsplit(streams2[0]["url"])
    rel2 = p2.path + "?" + p2.query
    resp_v2 = client.get(rel2, headers={"Range": "bytes=0-1000"})
    print("S2E2 video status:", resp_v2.status_code)
    assert resp_v2.status_code in (200, 206)
    print(">>> Season 2 Episode 2: SUCCESS PLAYABLE! <<<")

if __name__ == '__main__':
    test_hotd_multi_season()
