import sys
import os
import urllib.parse
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from nguonc_router import nguonc_router

app = FastAPI()
app.include_router(nguonc_router, prefix="/nguonc")

client = TestClient(app)

m3u8_url = "https://embed18.streamc.xyz/eyJoIjoiOWNjZTlhNzRmZmYxZjM5YTgzMmE4YzliNmI2NjQxOTYiLCJ0IjoiODA5MGM1OWFiYTIxZTllOWY2MDAyNzJlMmI5MjlmYTJjOWZhOGZkOGU2ZWRkMWMyMjE0YmEyNjhmYzY1YTg0ZSJ9?d=1"
embed_url = "https://embed18.streamc.xyz/embed.php?hash=9cce9a74fff1f39a832a8c9b6b664196"

res = client.get(f"/nguonc/stream_proxy?url={urllib.parse.quote(m3u8_url)}&referer={urllib.parse.quote(embed_url)}")
print("Status code:", res.status_code)
print("Content-Type:", res.headers.get("content-type"))
print("Content length:", len(res.content))
assert res.status_code == 200
assert len(res.content) > 100
print("PROXY SUCCESS!")
