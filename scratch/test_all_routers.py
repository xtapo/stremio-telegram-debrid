import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from fastapi.testclient import TestClient
from fastapi import FastAPI
from nguonc_router import (
    nguonc_router
)
from vsmov_router import vsmov_router
from topxx_router import topxx_router
from hhpanda_router import hhpanda_router

sys.stdout.reconfigure(encoding='utf-8')

app = FastAPI()
app.include_router(nguonc_router)
app.include_router(vsmov_router, prefix="/vsmov")
app.include_router(topxx_router, prefix="/topxx")
app.include_router(hhpanda_router, prefix="/hhpanda")

client = TestClient(app)

endpoints = [
    "/manifest.json",
    "/vsmov/manifest.json",
    "/topxx/manifest.json",
    "/hhpanda/manifest.json"
]

for ep in endpoints:
    r = client.get(ep)
    print(f"GET {ep} -> Status: {r.status_code}")
    if r.status_code != 200:
        print("  Error:", r.text)
