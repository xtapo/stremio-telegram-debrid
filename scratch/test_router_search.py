import sys
sys.path.insert(0, ".")
import asyncio
from fastapi.testclient import TestClient
from addon import app
import fourkhdhub_perf as perf

perf.CACHE.clear()
client = TestClient(app)
res = client.get("/4khdhub/catalog/movie/4khdhub_movies_latest/search=Avatar.json")
print("Status:", res.status_code)
print("Response JSON:", res.json())
