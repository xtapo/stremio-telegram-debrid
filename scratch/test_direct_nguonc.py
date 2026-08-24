import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from nguonc_router import nguonc_router

app = FastAPI()
app.include_router(nguonc_router, prefix="/nguonc")
app.include_router(nguonc_router)

client = TestClient(app)

def test_direct_stream():
    res = client.get("/nguonc/stream/movie/nguonc:su-that-cuoi-cung.json")
    assert res.status_code == 200
    streams = res.json().get("streams", [])
    print(f"Total streams: {len(streams)}")
    
    direct_stream = next((s for s in streams if "Direct" in s["name"]), None)
    proxy_stream = next((s for s in streams if "Proxy" in s["name"]), None)
    
    assert direct_stream, "Direct stream not found in streams response!"
    assert proxy_stream, "Proxy stream not found in streams response!"
    
    print("\n1. Direct Stream Info:")
    print("  Name:", direct_stream["name"])
    print("  Title:", direct_stream["title"])
    print("  URL:", direct_stream["url"])
    print("  Headers:", direct_stream.get("behaviorHints", {}).get("requestHeaders"))
    
    # Test Direct M3U8 Playlist
    direct_url = direct_stream["url"].replace("http://testserver", "")
    d_res = client.get(direct_url)
    assert d_res.status_code == 200
    d_text = d_res.text
    assert "#EXTM3U" in d_text
    print("\nDirect M3U8 Preview (Notice raw CDN URLs without stream_proxy):")
    sample_lines = [l for l in d_text.splitlines()[:10] if l]
    print("\n".join(sample_lines))
    
    # Verify that segment URLs in direct mode are NOT pointing to /stream_proxy
    segment_lines = [l for l in d_text.splitlines() if not l.startswith('#') and l]
    print("\nFirst direct segment URL:", segment_lines[0])
    assert "stream_proxy" not in segment_lines[0], "Direct playlist should contain raw CDN URLs, not proxy URLs!"
    assert segment_lines[0].startswith("http"), "Direct segment URL should be absolute http/https URL!"
    
    print("\n🎉 DIRECT STREAM VERIFICATION COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    test_direct_stream()
