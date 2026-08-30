import asyncio
import os
import sys
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import moviesdrive_perf as perf
from addon import app

client = TestClient(app)

def test_reacher_stream():
    perf.CACHE.clear()
    
    print("\n--- Testing Stream for Reacher Season 1 Episode 1 (tt9288030:1:1) ---")
    resp = client.get("/moviesdrive/stream/series/tt9288030:1:1.json")
    print("S1E1 status:", resp.status_code)
    data = resp.json()
    streams = data.get("streams", [])
    print(f"Got {len(streams)} streams for S1E1:")
    for s in streams:
        print(f"  Stream URL: {s.get('url')}")
    
    # Assert streams are for Season 1 (archives 6762, 6759, 6756)
    assert len(streams) > 0, "No streams found for Reacher S1E1!"
    for s in streams:
        url = s.get("url", "")
        assert "15695" not in url, "Wrongly got Season 4 archive for Season 1!"

    print("\n--- Testing Stream for Reacher Season 4 Episode 1 (tt9288030:4:1) ---")
    resp = client.get("/moviesdrive/stream/series/tt9288030:4:1.json")
    print("S4E1 status:", resp.status_code)
    data = resp.json()
    streams = data.get("streams", [])
    print(f"Got {len(streams)} streams for S4E1:")
    for s in streams:
        print(f"  Stream URL: {s.get('url')}")
    assert len(streams) > 0, "No streams found for Reacher S4E1!"
    for s in streams:
        url = s.get("url", "")
        assert "6762" not in url and "6759" not in url, "Wrongly got Season 1 archive for Season 4!"

    print("\n[SUCCESS] Stream endpoint returns exact match for each season!")

if __name__ == "__main__":
    test_reacher_stream()
