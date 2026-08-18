import asyncio
import os
import sys
import json
import time
import httpx
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vidking_router import (
    get_vidking_seed,
    get_vidking_client,
    VIDKING_API_BASE,
    VIDKING_SERVERS,
    decrypt_vidking_payload
)

async def debug():
    tmdb_id = 550
    seed = await get_vidking_seed(tmdb_id)
    print(f"Seed for TMDB {tmdb_id}: {seed}")

    client = get_vidking_client()
    for srv in VIDKING_SERVERS:
        endpoint = srv["endpoint"]
        name = srv["name"]
        params = {
            "title": "Fight Club",
            "mediaType": "movie",
            "year": "1999",
            "episodeId": "1",
            "seasonId": "1",
            "tmdbId": str(tmdb_id),
            "imdbId": "tt0137523",
            "enc": "2",
            "seed": seed,
            "_t": str(int(time.time() * 1000)),
        }
        url = f"{VIDKING_API_BASE}/{endpoint}"
        try:
            res = await client.get(url, params=params, timeout=10.0)
            print(f"\nServer {name} -> Status: {res.status_code}")
            if res.status_code == 200:
                raw = res.text.strip()
                print(f"Raw length: {len(raw)}, preview: {raw[:60]}")
                try:
                    decrypted = decrypt_vidking_payload(raw, seed, tmdb_id)
                    print(f"Decrypted: {decrypted[:200]}")
                except Exception as de:
                    print(f"Decrypt error: {de}")
            else:
                print(f"Error body: {res.text[:200]}")
        except Exception as e:
            print(f"Request error on {name}: {e}")

if __name__ == "__main__":
    asyncio.run(debug())
