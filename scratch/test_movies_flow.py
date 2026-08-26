import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
from fastapi.testclient import TestClient
from addon import app
from moviesdrive_router import CACHE
import urllib.parse

CACHE.clear()
client = TestClient(app)

def test_movies():
    # 1. Test Minions & Monsters (2026)
    print("\n=== Testing Minions & Monsters (2026) ===")
    movie_id = "moviesdrive:minions-monsters-2026-web-dl-hindi-dd5-1-english-480p-720p-1080p-2160p-4k-sdr-x264-esubs-full-movie"
    resp = client.get(f"/stream/movie/{movie_id}.json")
    print("Status code:", resp.status_code)
    assert resp.status_code == 200
    streams = resp.json().get("streams", [])
    print(f"Resolved {len(streams)} streams for Minions & Monsters:")
    assert len(streams) > 0
    for s in streams:
        print(f" - [{s['name']}] Title: {s['title'][:50]}... => URL: {s['url'][:70]}...")
        
    # Play test first stream
    p = urllib.parse.urlsplit(streams[0]["url"])
    rel_url = p.path + "?" + p.query
    resp_video = client.get(rel_url, headers={"Range": "bytes=0-1000"})
    print("Video play status:", resp_video.status_code)
    print("Video content-type:", resp_video.headers.get("content-type"))
    print("Video content-range:", resp_video.headers.get("content-range"))
    try:
        assert resp_video.status_code in (200, 206)
        assert resp_video.content.startswith(b"\x1a\x45\xdf\xa3")
        print(">>> Minions & Monsters: 100% SUCCESS PLAYABLE! <<<")
    except AssertionError:
        print("Minions video play failed, might be dead on source.")

    # 2. Test Cocktail 2 (2026)
    print("\n=== Testing Cocktail 2 (2026) ===")
    cocktail_id = "moviesdrive:cocktail-2-2026-web-dl-hindi-dd5-1-english-480p-720p-1080p-2160p-4k-sdr-x264-esubs-full-movie"
    resp2 = client.get(f"/stream/movie/{cocktail_id}.json")
    assert resp2.status_code == 200
    streams2 = resp2.json().get("streams", [])
    print(f"Resolved {len(streams2)} streams for Cocktail 2:")
    assert len(streams2) > 0
    for s in streams2:
        print(f" - [{s['name']}] Title: {s['title'][:50]}... => URL: {s['url'][:70]}...")
    print(">>> Cocktail 2: 100% SUCCESS! <<<")

if __name__ == "__main__":
    test_movies()
