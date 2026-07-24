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

# Test the exact request Stremio sent:
res = client.get("/meta/movie/vsmov%3Anguu-lang-chuc-nu.json")
print("Status code for /meta/movie/vsmov%3Anguu-lang-chuc-nu.json:", res.status_code)
print("Response JSON keys:", list(res.json().keys()))
print("Meta content:", res.json().get("meta"))
