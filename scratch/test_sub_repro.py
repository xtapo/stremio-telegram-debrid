import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
from fastapi.testclient import TestClient
from addon import app

client = TestClient(app)

def test_subtitles_error():
    print("\n1. Testing /subtitles/movie/tt26657236.json...")
    r1 = client.get("/subtitles/movie/tt26657236.json")
    print("Status:", r1.status_code)
    print("Content:", r1.json())
    
    print("\n2. Testing /subtitles/movie/tt26657236/videoHash%3D1234.json...")
    r2 = client.get("/subtitles/movie/tt26657236/videoHash%3D1234.json")
    print("Status:", r2.status_code)
    print("Content:", r2.json())

if __name__ == '__main__':
    test_subtitles_error()
