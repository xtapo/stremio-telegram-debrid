import json
from scratch.test_source_decrypt import Pf, client, endpoints, seed, params, tmdb_id

res = client.get("https://api.speedracelight.com/cdn/sources-with-title", params=params)
data = json.loads(Pf(res.text.strip(), seed, tmdb_id))

print("Sources:", json.dumps(data.get("sources", []), indent=2))
print("Subtitles count:", len(data.get("subtitles", [])))
if "subtitles" in data:
    for sub in data["subtitles"][:5]:
        print("  Sub:", sub)
