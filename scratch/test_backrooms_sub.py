import sys
sys.path.insert(0, ".")
from config import Config
print("Config.ENABLE_SUBTITLES from .env:", Config.ENABLE_SUBTITLES)
print("Config.AUTO_VIET_SUB from .env:", Config.AUTO_VIET_SUB)
from fastapi.testclient import TestClient
from addon import app
import fourkhdhub_perf as perf

perf.CACHE.clear()
client = TestClient(app)
res = client.get("/4khdhub/subtitles/movie/4khdhub%3Abackrooms-movie-7787/filename%3Dbackrooms.movie.7787.mkv.json")
print("Status:", res.status_code)
subs = res.json().get("subtitles", [])
print(f"Total Subtitles returned: {len(subs)}")
for s in subs[:6]:
    name = s.get('name') or s.get('id')
    print(f"  * [{s.get('lang')}] {name.encode('ascii', 'replace').decode('ascii')} -> {s.get('url')[:60]}...")
