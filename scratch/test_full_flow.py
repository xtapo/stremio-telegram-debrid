import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
from fastapi.testclient import TestClient
from addon import app
from moviesdrive_router import CACHE
import urllib.parse

CACHE.clear()
client = TestClient(app)

def test_full_flow():
    # 1. Test The East Palace Ep 2
    print("\n=== Testing The East Palace S1E2 ===")
    resp_ep2 = client.get("/stream/series/moviesdrive:the-east-palace-season-1-2026:1:2.json")
    assert resp_ep2.status_code == 200
    streams_ep2 = resp_ep2.json().get("streams", [])
    print(f"Got {len(streams_ep2)} streams for Ep 2:")
    assert len(streams_ep2) > 0
    for s in streams_ep2:
        print(f" -> {s['name']}: {s['title'][:40]} => {s['url'][:80]}...")
        # Check no .zip files in URLs
        assert ".zip" not in s['url'].lower()
        
    # 2. Test playing first stream of Ep 2
    p = urllib.parse.urlsplit(streams_ep2[0]["url"])
    rel_url = p.path + "?" + p.query
    resp_v2 = client.get(rel_url, headers={"Range": "bytes=0-1000"})
    print("Ep 2 video play status:", resp_v2.status_code)
    print("Ep 2 video content-type:", resp_v2.headers.get("content-type"))
    print("Ep 2 video content-range:", resp_v2.headers.get("content-range"))
    assert resp_v2.status_code in (200, 206)
    assert resp_v2.content.startswith(b"\x1a\x45\xdf\xa3")
    print(">>> The East Palace Ep 2: 100% SUCCESS PLAYABLE! <<<")

    # 3. Test Spooky in Love Ep 1
    print("\n=== Testing Spooky in Love S1E1 ===")
    resp_spooky = client.get("/stream/series/moviesdrive:spooky-in-love-season-1-2026:1:1.json")
    assert resp_spooky.status_code == 200
    streams_sp = resp_spooky.json().get("streams", [])
    print(f"Got {len(streams_sp)} streams for Spooky in Love:")
    assert len(streams_sp) > 0
    for s in streams_sp:
        assert ".zip" not in s['url'].lower()
        print(f" -> {s['name']}: {s['title'][:40]} => {s['url'][:80]}...")
        
    # Play first stream of Spooky
    p_sp = urllib.parse.urlsplit(streams_sp[0]["url"])
    rel_sp = p_sp.path + "?" + p_sp.query
    resp_v_sp = client.get(rel_sp, headers={"Range": "bytes=0-1000"})
    print("Spooky video play status:", resp_v_sp.status_code)
    print("Spooky video content-type:", resp_v_sp.headers.get("content-type"))
    print("Spooky video content-range:", resp_v_sp.headers.get("content-range"))
    assert resp_v_sp.status_code in (200, 206)
    assert resp_v_sp.content.startswith(b"\x1a\x45\xdf\xa3")
    print(">>> Spooky in Love: 100% SUCCESS PLAYABLE! <<<")

if __name__ == "__main__":
    test_full_flow()
