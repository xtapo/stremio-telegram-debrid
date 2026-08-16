import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from fastapi.testclient import TestClient
from addon import app

client = TestClient(app)

def test_moviesdrive_proxy_stream():
    # 1. Get stream url for Spooky in Love
    resp = client.get("/moviesdrive/stream/series/moviesdrive:spooky-in-love-season-1-2026:1:1.json")
    assert resp.status_code == 200
    streams = resp.json().get("streams", [])
    assert len(streams) > 0
    proxy_url = streams[0]["url"]
    print("Found stream proxy URL:", proxy_url)

    # Extract relative path from proxy_url
    import urllib.parse
    p = urllib.parse.urlsplit(proxy_url)
    rel_url = p.path + "?" + p.query

    # 2. Test Range request
    print("Testing Range 0-1024 on stream proxy...")
    resp_range = client.get(rel_url, headers={"Range": "bytes=0-1024"})
    print("Proxy Response status:", resp_range.status_code)
    print("Headers Content-Range:", resp_range.headers.get("content-range"))
    print("Headers Content-Type:", resp_range.headers.get("content-type"))
    print("Bytes read:", len(resp_range.content))
    assert resp_range.status_code in (200, 206)
    assert len(resp_range.content) > 0
    print("Stream proxy test passed cleanly without Content-Length crash!")

if __name__ == "__main__":
    test_moviesdrive_proxy_stream()
