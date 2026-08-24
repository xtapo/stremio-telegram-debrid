import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from addon import app

client = TestClient(app)

def test_proxy_and_player():
    print("=== Testing /tvrun/tv ===")
    r = client.get("/tvrun/tv")
    assert r.status_code == 200
    print("HTML length:", len(r.text))
    
    print("\n=== Testing /tvrun/api/countries ===")
    r2 = client.get("/tvrun/api/countries")
    assert r2.status_code == 200
    print("Countries count:", len(r2.json().get("countries", [])))
    
    print("\n=== Testing /tvrun/api/channels?source=freetv ===")
    r3 = client.get("/tvrun/api/channels?source=freetv")
    assert r3.status_code == 200
    channels = r3.json().get("channels", [])
    print("FreeTV channels:", len(channels))
    
    print("\n=== Testing /tvrun/stream_proxy ===")
    sample_url = channels[0]["url"] if channels else "https://live20.bozztv.com/akamaissh101/ssh101/oasistv123/playlist.m3u8"
    proxy_r = client.get(f"/tvrun/stream_proxy?url={sample_url}")
    print("Proxy status:", proxy_r.status_code)
    print("Proxy Content-Type:", proxy_r.headers.get("Content-Type"))
    print("Proxy Access-Control-Allow-Origin:", proxy_r.headers.get("Access-Control-Allow-Origin"))
    assert proxy_r.status_code in [200, 302, 502]
    
    print("\n🎉 TVRUN PROXY & PLAYER TESTS PASSED!")

if __name__ == "__main__":
    test_proxy_and_player()
