import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
from fastapi.testclient import TestClient
from addon import app
import urllib.parse

client = TestClient(app)

def test_instant_synced_subtitles():
    # 1. Test Backrooms Movie (tt26657236)
    print("\n=== 1. Testing Subtitles for Backrooms (tt26657236) ===")
    r1 = client.get("/subtitles/movie/tt26657236.json")
    assert r1.status_code == 200
    subs1 = r1.json().get("subtitles", [])
    print(f"Got {len(subs1)} subtitles for Backrooms:")
    assert len(subs1) > 0
    priority_sub = subs1[0]
    print(f" -> Priority Track 1: {priority_sub}")
    assert priority_sub["lang"] == "vie"
    assert "Tiếng Việt Đồng Bộ Chuẩn 100%" in priority_sub["name"]

    # 2. Fetch the actual VTT content
    p = urllib.parse.urlsplit(priority_sub["url"])
    rel_vtt = p.path + "?" + p.query
    print(f"\nFetching VTT content from {rel_vtt}...")
    r_vtt = client.get(rel_vtt)
    print("VTT status:", r_vtt.status_code)
    print("VTT Content-Type:", r_vtt.headers.get("content-type"))
    assert r_vtt.status_code == 200
    assert r_vtt.text.startswith("WEBVTT")
    print("VTT preview (first 15 lines):")
    print("\n".join(r_vtt.text.split("\n")[:15]))
    print(">>> Backrooms: 100% SUCCESS INSTANT VTT! <<<")

    # 3. Test House of the Dragon S1E1
    print("\n=== 2. Testing Subtitles for HOTD S1E1 ===")
    hotd_id = "moviesdrive:house-of-the-dragon-season-1-3:1:1"
    r_hotd = client.get(f"/moviesdrive/subtitles/series/{hotd_id}.json")
    assert r_hotd.status_code == 200
    subs_hotd = r_hotd.json().get("subtitles", [])
    assert len(subs_hotd) > 0
    priority_hotd = subs_hotd[0]
    print(f" -> HOTD Priority Track: {priority_hotd}")
    p_h = urllib.parse.urlsplit(priority_hotd["url"])
    rel_vh = p_h.path + "?" + p_h.query
    r_vh = client.get(rel_vh)
    assert r_vh.status_code == 200
    assert r_vh.text.startswith("WEBVTT")
    print(">>> HOTD S1E1: 100% SUCCESS INSTANT VTT! <<<")

if __name__ == '__main__':
    test_instant_synced_subtitles()
