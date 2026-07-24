import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from nguonc_router import nguonc_router

app = FastAPI()
app.include_router(nguonc_router, prefix="/nguonc")

client = TestClient(app)

res = client.get("/nguonc/stream_proxy?url=https%3A%2F%2Fembed18.streamc.xyz%2Fembed.php%3Fhash%3D9cce9a74fff1f39a832a8c9b6b664196")
print("Status code:", res.status_code)
print("Content length preview:", len(res.content))
assert res.status_code == 200
print("✅ Proxy test passed!")
