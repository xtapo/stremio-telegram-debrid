import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from addon import app

client = TestClient(app)

manifests = [
    "/manifest.json",
    "/iptv/manifest.json",
    "/tvrun/manifest.json",
    "/film4k/manifest.json",
    "/ernax/manifest.json",
    "/vidking/manifest.json",
    "/hdtoday/manifest.json",
    "/hdhub4u/manifest.json",
    "/moviesdrive/manifest.json",
    "/hhpanda/manifest.json",
    "/topxx/manifest.json",
    "/vsmov/manifest.json",
    "/nguonc/manifest.json",
]

print("=== VERIFYING ALL MANIFEST ENDPOINTS ===")
for path in manifests:
    r = client.get(path)
    print(f"GET {path:30} -> Status: {r.status_code}")
    assert r.status_code == 200

print("\n=== VERIFYING WEB PLAYERS ===")
web_players = [
    "/iptv/tv",
    "/iptv/player",
    "/tvrun/tv",
    "/tvrun/player",
    "/film4k/tv",
]
for path in web_players:
    r = client.get(path)
    print(f"GET {path:30} -> Status: {r.status_code}")
    assert r.status_code == 200

print("\n🎉 ALL ADDON MANIFESTS & WEB PLAYERS ARE OPERATIONAL!")
