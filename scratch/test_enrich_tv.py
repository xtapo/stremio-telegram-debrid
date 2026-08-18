import asyncio
import httpx

async def test_enrich():
    client = httpx.AsyncClient(headers={'User-Agent': 'Mozilla/5.0'}, timeout=10.0)
    
    # 1. Fetch TV popular
    r = await client.get('https://db.speedracelight.com/3/tv/popular?page=1')
    shows = r.json().get('results', [])[:5]
    
    tasks = [
        client.get(f"https://db.speedracelight.com/3/tv/{s['id']}?append_to_response=external_ids")
        for s in shows
    ]
    res_list = await asyncio.gather(*tasks, return_exceptions=True)
    
    for s, res in zip(shows, res_list):
        if not isinstance(res, Exception) and res.status_code == 200:
            data = res.json()
            imdb = data.get("external_ids", {}).get("imdb_id")
            print(f"Show: {s.get('name')} -> IMDb ID: {imdb}")
            
    await client.aclose()

asyncio.run(test_enrich())
