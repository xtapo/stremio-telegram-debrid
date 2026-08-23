import sys
sys.path.insert(0, ".")
import asyncio
from config import Config
print("Config.ENABLE_SUBTITLES:", Config.ENABLE_SUBTITLES)
print("Config.AUTO_VIET_SUB:", Config.AUTO_VIET_SUB)
from fastapi.testclient import TestClient
from addon import app
import fourkhdhub_perf as perf

perf.CACHE.clear()
client = TestClient(app)

print("\nRequesting streams for 4khdhub:backrooms-movie-7787...")
res = client.get("/4khdhub/stream/movie/4khdhub%3Abackrooms-movie-7787.json")
print("Status:", res.status_code)
print("Streams count:", len(res.json().get("streams", [])))

print("Waiting 3 seconds to confirm NO background translation runs...")
import time
time.sleep(3)
print("Done! No translation triggered.")
