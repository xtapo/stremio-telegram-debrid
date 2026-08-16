import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
from fastapi.testclient import TestClient
from addon import app
from moviesdrive_router import CACHE

CACHE.clear()
client = TestClient(app)

def test_hotd_imdb():
    # House of the Dragon Season 1 Episode 1: tt11198330:1:1
    print("\nTesting House of the Dragon S1E1 by IMDb ID...")
    resp = client.get("/moviesdrive/stream/series/tt11198330:1:1.json")
    print("Status:", resp.status_code)
    assert resp.status_code == 200
    streams = resp.json().get("streams", [])
    print(f"Resolved {len(streams)} streams for House of the Dragon:")
    for s in streams:
        print(f" - [{s['name']}] Title: {s['title'][:50]} => URL: {s['url'][:70]}...")

if __name__ == '__main__':
    test_hotd_imdb()
