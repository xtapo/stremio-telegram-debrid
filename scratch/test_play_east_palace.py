import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
from fastapi.testclient import TestClient
from addon import app

client = TestClient(app)

def test_play_east_palace():
    resp = client.get("/stream/series/moviesdrive:the-east-palace-season-1-2026:1:1.json")
    assert resp.status_code == 200
    streams = resp.json().get("streams", [])
    assert len(streams) > 0
    
    first_stream_url = streams[0]["url"]
    print("Testing play stream:", first_stream_url)
    
    import urllib.parse
    p = urllib.parse.urlsplit(first_stream_url)
    rel_url = p.path + "?" + p.query
    
    # Request Range 0-1024
    resp_video = client.get(rel_url, headers={"Range": "bytes=0-1024"})
    print("Status:", resp_video.status_code)
    print("Content-Type:", resp_video.headers.get("content-type"))
    print("Content-Range:", resp_video.headers.get("content-range"))
    print("Magic bytes hex:", resp_video.content[:16].hex())
    assert resp_video.status_code in (200, 206)
    assert resp_video.content.startswith(b"\x1a\x45\xdf\xa3")
    print(">>> 100% SUCCESS: REAL MKV STREAM PLAYABLE! <<<")

if __name__ == "__main__":
    test_play_east_palace()
