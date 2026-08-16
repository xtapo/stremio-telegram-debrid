import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
from fastapi.testclient import TestClient
from addon import app

client = TestClient(app)

def test_series_sub():
    resp = client.get("/moviesdrive/subtitles/series/moviesdrive:the-east-palace-season-1-2026:1:1.json")
    print("East Palace status:", resp.status_code)
    subs = resp.json().get("subtitles", [])
    print(f"Found {len(subs)} subtitles for East Palace S1E1:")
    for s in subs[:3]:
        print(f"  - Lang: {s.get('lang')}, URL: {s.get('url')[:60]}...")

if __name__ == '__main__':
    test_series_sub()
