import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from vidking_router import VIDKING_SERVERS, fetch_and_decrypt_server, get_vidking_seed

async def test_all_qualities(tmdb_id=533535):
    seed = await get_vidking_seed(tmdb_id)
    print("Seed:", seed)
    if not seed:
        return
        
    for srv in VIDKING_SERVERS:
        streams = await fetch_and_decrypt_server(
            server_cfg=srv,
            tmdb_id=tmdb_id,
            media_type="movie",
            title="Deadpool & Wolverine",
            year="2024",
            imdb_id="tt6263850",
            seed=seed,
            base_url="http://localhost:7860"
        )
        print(f"\n--- Server: {srv['name']} (returned {len(streams)} streams) ---")
        for s in streams:
            name_clean = s.get("name", "").encode("ascii", "ignore").decode("ascii").replace("\n", " | ")
            title_clean = s.get("title", "").split("\n")[0].encode("ascii", "ignore").decode("ascii")
            print(" Name:", name_clean)
            print(" Title:", title_clean)
            print(" URL:", s.get("url")[:80])

if __name__ == "__main__":
    asyncio.run(test_all_qualities())
