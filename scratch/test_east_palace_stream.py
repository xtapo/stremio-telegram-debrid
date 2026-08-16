import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from fastapi.testclient import TestClient
from addon import app
from moviesdrive_router import CACHE

CACHE.clear()

client = TestClient(app)

def test_east_palace():
    resp = client.get("/stream/series/moviesdrive:the-east-palace-season-1-2026:1:1.json")
    print("East Palace S1E1 status:", resp.status_code)
    assert resp.status_code == 200
    streams = resp.json().get("streams", [])
    print(f"Resolved {len(streams)} streams for East Palace:")
    for s in streams:
        print(f" - [{s.get('name')}] => {s.get('title')}\n   URL: {s.get('url')[:100]}...\n")
    assert len(streams) > 0

if __name__ == "__main__":
    test_east_palace()
