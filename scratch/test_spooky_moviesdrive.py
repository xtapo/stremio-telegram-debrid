import sys, os, urllib.parse
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
from fastapi.testclient import TestClient
from addon import app
from moviesdrive_router import CACHE

CACHE.clear()
client = TestClient(app)

def test():
    movie_id = "moviesdrive:spooky-in-love-season-1-2026-hindi-english-korean-1080p-x264-1-4gb-e"
    print(f"Testing {movie_id}")
    resp = client.get(f"/stream/series/{movie_id}:1:1.json")
    print(resp.status_code)
    streams = resp.json().get("streams", [])
    print(f"Found {len(streams)} streams")
    for s in streams:
        print(s["name"], s["url"])
    if streams:
        p = urllib.parse.urlsplit(streams[0]["url"])
        rel_url = p.path + "?" + p.query
        print("Playing:", rel_url)
        resp_video = client.get(rel_url, headers={"Range": "bytes=0-1000"})
        print(resp_video.status_code)
        if resp_video.status_code in (200, 206):
            print("Success:", resp_video.content[:10])

test()
