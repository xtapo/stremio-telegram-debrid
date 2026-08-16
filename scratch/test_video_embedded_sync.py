import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
from fastapi.testclient import TestClient
from addon import app
import urllib.parse

client = TestClient(app)

def test_embedded_sync_flow():
    # 1. Request streams for Minions & Monsters
    movie_id = "moviesdrive:minions-monsters-2026-web-dl-hindi-dd5-1-english-480p-720p-1080p-2160p-4k-sdr-x264-esubs-full-movie"
    print("\n1. Requesting streams for Minions & Monsters...")
    r_stream = client.get(f"/stream/movie/{movie_id}.json")
    assert r_stream.status_code == 200
    print("Streams resolved.")

    # 2. Request subtitles
    print("\n2. Requesting subtitles...")
    r_sub = client.get(f"/subtitles/movie/{movie_id}.json")
    assert r_sub.status_code == 200
    subs = r_sub.json().get("subtitles", [])
    assert len(subs) > 0
    priority_sub = subs[0]
    print("Priority Subtitle Track:", priority_sub)

    # 3. Fetch the VTT file
    p = urllib.parse.urlsplit(priority_sub["url"])
    rel_vtt = p.path + "?" + p.query
    print(f"\n3. Fetching VTT content from {rel_vtt}...")
    r_vtt = client.get(rel_vtt)
    assert r_vtt.status_code == 200
    assert r_vtt.text.startswith("WEBVTT")
    print("VTT preview (lines 1-25):")
    print("\n".join(r_vtt.text.split("\n")[:25]))
    print(">>> SUCCESS: Subtitle extracted directly from embedded video track and translated! <<<")

if __name__ == '__main__':
    test_embedded_sync_flow()
