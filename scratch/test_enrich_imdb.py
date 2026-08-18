import asyncio
import time
import httpx

client = httpx.AsyncClient(
    headers={'User-Agent': 'Mozilla/5.0'},
    timeout=httpx.Timeout(10.0, connect=3.0)
)

async def test():
    # 1. Fetch popular movies
    t0 = time.time()
    r = await client.get('https://db.speedracelight.com/3/movie/popular?page=1')
    movies = r.json().get('results', [])[:10]
    print(f"Fetched {len(movies)} movies in {time.time()-t0:.2f}s")
    
    # 2. Fetch external_ids in parallel for these 10 movies
    t1 = time.time()
    tasks = [
        client.get(f"https://db.speedracelight.com/3/movie/{m['id']}?append_to_response=external_ids")
        for m in movies
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    t2 = time.time()
    print(f"Fetched 10 external_ids in parallel in {t2-t1:.2f}s")
    for m, res in zip(movies, results):
        if not isinstance(res, Exception) and res.status_code == 200:
            data = res.json()
            imdb_id = data.get("external_ids", {}).get("imdb_id")
            print(f"  {m.get('title')} (TMDB {m.get('id')}) -> IMDb: {imdb_id}")

    await client.aclose()

if __name__ == '__main__':
    asyncio.run(test())
