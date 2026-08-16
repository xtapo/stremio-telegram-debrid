import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
from fastapi.testclient import TestClient
from addon import app

client = TestClient(app)

print("1. Testing GET /subtitles/vtt/tt11198330:1:1.vtt?type=series ...")
r1 = client.get("/subtitles/vtt/tt11198330:1:1.vtt?type=series")
print("GET status:", r1.status_code)

print("\n2. Testing HEAD /subtitles/vtt/tt11198330:1:1.vtt?type=series ...")
r2 = client.head("/subtitles/vtt/tt11198330:1:1.vtt?type=series")
print("HEAD status:", r2.status_code)
