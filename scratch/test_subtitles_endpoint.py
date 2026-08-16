import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
from fastapi.testclient import TestClient
from addon import app
from moviesdrive_router import CACHE

CACHE.clear()
client = TestClient(app)

def test_subtitles_endpoint():
    md_id = "moviesdrive:minions-monsters-2026-web-dl-hindi-dd5-1-english-480p-720p-1080p-2160p-4k-sdr-x264-esubs-full-movie"
    
    print("\n1. Testing /moviesdrive/subtitles/movie/...")
    resp1 = client.get(f"/moviesdrive/subtitles/movie/{md_id}.json")
    assert resp1.status_code == 200
    subs1 = resp1.json().get("subtitles", [])
    print(f"Found {len(subs1)} subtitles from /moviesdrive/subtitles:")
    assert len(subs1) > 0
    for s in subs1[:3]:
        print(f"  - Lang: {s.get('lang')}, URL: {s.get('url')[:60]}...")
        
    print("\n2. Testing root /subtitles/movie/...")
    resp2 = client.get(f"/subtitles/movie/{md_id}.json")
    assert resp2.status_code == 200
    subs2 = resp2.json().get("subtitles", [])
    print(f"Found {len(subs2)} subtitles from root /subtitles:")
    assert len(subs2) > 0
    print(">>> Subtitles endpoints verified 100% SUCCESS! <<<")

if __name__ == '__main__':
    test_subtitles_endpoint()
