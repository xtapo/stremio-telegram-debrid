import sys
import os
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding='utf-8')

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nguonc_router import nguonc_router
from vsmov_router import vsmov_router



app = FastAPI()
app.include_router(nguonc_router)
app.include_router(vsmov_router, prefix="/vsmov")

client = TestClient(app)

res1 = client.get("/nguonc/manifest.json")
print("NguonC manifest:", res1.status_code)

res2 = client.get("/vsmov/manifest.json")
print("VSMov manifest:", res2.status_code, res2.json().get("name"))

assert res1.status_code == 200
assert res2.status_code == 200
print("\n✅ BOTH MANIFEST ENDPOINTS WORKING PERFECTLY!")
