import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import asyncio
from fastapi.testclient import TestClient
from fastapi import FastAPI
from moviesdrive_router import moviesdrive_router

app = FastAPI()
app.include_router(moviesdrive_router, prefix="/moviesdrive")

client = TestClient(app)

def test_manifest():
    resp = client.get("/moviesdrive/manifest.json")
    print("Manifest status:", resp.status_code)
    data = resp.json()
    assert data["id"] == "com.stremio.moviesdrive.addon"
    print("Manifest ID:", data["id"], "| Catalogs count:", len(data["catalogs"]))

def test_catalog_search():
    resp = client.get("/moviesdrive/catalog/movie/moviesdrive_movies_latest.json?search=inception")
    print("Catalog search status:", resp.status_code)
    data = resp.json()
    metas = data.get("metas", [])
    print(f"Found {len(metas)} catalog items for 'inception'")
    if metas:
        print("First item:", metas[0])

def test_catalog_4k():
    resp = client.get("/moviesdrive/catalog/movie/moviesdrive_movies_4k.json")
    print("Catalog 4K status:", resp.status_code)
    data = resp.json()
    metas = data.get("metas", [])
    print(f"Found {len(metas)} 4K items")
    if metas:
        print("First 4K item:", metas[0])

def test_meta():
    resp = client.get("/moviesdrive/meta/movie/moviesdrive:inception-2010.json")
    print("Meta status:", resp.status_code)
    data = resp.json()
    meta = data.get("meta", {})
    print("Meta name:", meta.get("name"), "| Poster:", meta.get("poster")[:60] if meta.get("poster") else "None")

def test_stream_custom_id():
    resp = client.get("/moviesdrive/stream/movie/moviesdrive:inception-2010.json")
    print("Stream custom ID status:", resp.status_code)
    data = resp.json()
    streams = data.get("streams", [])
    print(f"Resolved {len(streams)} streams for inception-2010:")
    for s in streams[:4]:
        print(f" - {s.get('name')} | {s.get('title')[:40]} -> {s.get('url')[:60]}...")

def test_stream_imdb_id():
    # Inception IMDb ID is tt1375666
    resp = client.get("/moviesdrive/stream/movie/tt1375666.json")
    print("Stream IMDb ID status:", resp.status_code)
    data = resp.json()
    streams = data.get("streams", [])
    print(f"Resolved {len(streams)} streams for IMDb tt1375666 (Inception):")
    for s in streams[:4]:
        print(f" - {s.get('name')} | {s.get('title')[:40]} -> {s.get('url')[:60]}...")

def main():
    print("=== Testing Manifest ===")
    test_manifest()
    print("\n=== Testing Catalog Search ===")
    test_catalog_search()
    print("\n=== Testing Catalog 4K ===")
    test_catalog_4k()
    print("\n=== Testing Meta ===")
    test_meta()
    print("\n=== Testing Stream (Custom ID) ===")
    test_stream_custom_id()
    print("\n=== Testing Stream (IMDb ID) ===")
    test_stream_imdb_id()

if __name__ == "__main__":
    main()
