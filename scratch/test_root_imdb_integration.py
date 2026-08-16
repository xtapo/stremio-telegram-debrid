import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
from fastapi.testclient import TestClient
from addon import app

client = TestClient(app)

def test_root_imdb_integration():
    # 1. House of the Dragon S1E1
    print("\nTesting root stream for House of the Dragon (tt11198330:1:1)...")
    resp = client.get("/stream/series/tt11198330:1:1.json")
    assert resp.status_code == 200
    streams = resp.json().get("streams", [])
    print(f"Resolved {len(streams)} streams from root addon:")
    md_streams = [s for s in streams if "MoviesDrive" in s.get("name", "")]
    print(f"Found {len(md_streams)} MoviesDrive streams in root addon!")
    assert len(md_streams) > 0
    for s in md_streams[:5]:
        print(f" - [{s['name']}] {s['title'][:40]} => {s['url'][:60]}...")

    # 2. Deadpool & Wolverine Movie
    print("\nTesting root stream for Deadpool (tt6263850)...")
    resp_dp = client.get("/stream/movie/tt6263850.json")
    assert resp_dp.status_code == 200
    streams_dp = resp_dp.json().get("streams", [])
    print(f"Resolved {len(streams_dp)} streams for Deadpool:")
    md_dp = [s for s in streams_dp if "MoviesDrive" in s.get("name", "")]
    print(f"Found {len(md_dp)} MoviesDrive streams for Deadpool!")
    assert len(md_dp) > 0

if __name__ == '__main__':
    test_root_imdb_integration()
