import asyncio
import httpx
from fastapi import FastAPI
from kkphim_router import kkphim_router, search_kkphim
from ridomovies_router import ridomovies_router, search_ridomovies
from yanhh3d_router import yanhh3d_router, search_yanhh3d

app = FastAPI()
app.include_router(kkphim_router, prefix="/kkphim")
app.include_router(ridomovies_router, prefix="/ridomovies")
app.include_router(yanhh3d_router, prefix="/yanhh3d")

async def run_tests():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("=== 1. Testing KKPhim Endpoints ===")
        r = await client.get("/kkphim/manifest.json")
        print("  Manifest status:", r.status_code, "Catalogs:", len(r.json().get("catalogs", [])))
        
        r = await client.get("/kkphim/catalog/movie/kkphim_phim_le.json")
        metas = r.json().get("metas", [])
        print("  Catalog movie items:", len(metas))
        if metas:
            first_id = metas[0]["id"]
            print("  First item:", metas[0]["name"], "id:", first_id)
            r_meta = await client.get(f"/kkphim/meta/movie/{first_id}.json")
            print("  Meta status:", r_meta.status_code, "Meta title:", r_meta.json().get("meta", {}).get("name"))
            
            r_stream = await client.get(f"/kkphim/stream/movie/{first_id}.json")
            streams = r_stream.json().get("streams", [])
            print("  Streams count:", len(streams))
            if streams:
                print("  Sample stream:", streams[0].get("name"), "->", streams[0].get("url") or streams[0].get("externalUrl"))

        print("\n=== 2. Testing RidoMovies Endpoints ===")
        r = await client.get("/ridomovies/manifest.json")
        print("  Manifest status:", r.status_code, "Catalogs:", len(r.json().get("catalogs", [])))
        r = await client.get("/ridomovies/catalog/movie/ridomovies_movies.json")
        metas = r.json().get("metas", [])
        print("  Catalog movie items:", len(metas))
        if metas:
            first_id = metas[0]["id"]
            print("  First item:", metas[0]["name"], "id:", first_id)
            r_meta = await client.get(f"/ridomovies/meta/movie/{first_id}.json")
            print("  Meta status:", r_meta.status_code, "Meta title:", r_meta.json().get("meta", {}).get("name"))
            r_stream = await client.get(f"/ridomovies/stream/movie/{first_id}.json")
            print("  Streams count:", len(r_stream.json().get("streams", [])))

        print("\n=== 3. Testing Yanhh3d Endpoints ===")
        r = await client.get("/yanhh3d/manifest.json")
        print("  Manifest status:", r.status_code, "Catalogs:", len(r.json().get("catalogs", [])))
        r = await client.get("/yanhh3d/catalog/series/yanhh3d_4k.json")
        metas = r.json().get("metas", [])
        print("  Catalog series items:", len(metas))
        if metas:
            first_id = metas[0]["id"]
            print("  First item:", metas[0]["name"], "id:", first_id)
            r_meta = await client.get(f"/yanhh3d/meta/series/{first_id}.json")
            print("  Meta status:", r_meta.status_code, "Videos:", len(r_meta.json().get("meta", {}).get("videos", [])))

        print("\n=== 4. Testing Unified Search Helpers ===")
        s_kk = await search_kkphim("conan", max_results=3)
        print("  KKPhim search 'conan':", len(s_kk), "items")
        s_rido = await search_ridomovies("avatar", max_results=3)
        print("  RidoMovies search 'avatar':", len(s_rido), "items")
        s_yanhh = await search_yanhh3d("tien", max_results=3)
        print("  Yanhh3d search 'tien':", len(s_yanhh), "items")

if __name__ == "__main__":
    asyncio.run(run_tests())
