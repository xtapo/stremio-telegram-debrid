import sys
import os
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding='utf-8')

from vsmov_router import vsmov_router
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()
app.include_router(vsmov_router)

client = TestClient(app)

res = client.get("/vsmov/meta/movie/vsmov%3Aduong-ba-ho-diem-thu-huong-17848938329438.json")
print("Status code:", res.status_code)
print("Keys:", list(res.json().get("meta", {}).keys()))
print("Meta name:", res.json().get("meta", {}).get("name"))
