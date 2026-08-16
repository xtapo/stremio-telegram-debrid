import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from fastapi.testclient import TestClient
from addon import app

client = TestClient(app)

def test_spooky_series():
    resp = client.get("/stream/series/moviesdrive:spooky-in-love-season-1-2026:1:1.json")
    assert resp.status_code == 200
    streams = resp.json().get("streams", [])
    print(f"Resolved {len(streams)} streams:")
    for s in streams:
        print(f"[{s.get('name')}] Title: {s.get('title')}\nURL: {s.get('url')[:120]}...\n")

if __name__ == "__main__":
    test_spooky_series()
