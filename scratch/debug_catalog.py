import asyncio
import httpx
from ridomovies_router import search_ridomovies, ridomovies_catalog_handler
from clbphimxua_router import search_clbphimxua, clbphimxua_catalog_handler
from yanhh3d_router import search_yanhh3d, yanhh3d_catalog_handler

async def test_inspect():
    print("--- Testing Rido ---")
    r = await ridomovies_catalog_handler("movie", "ridomovies_movies")
    print("Rido catalog:", len(r.get("metas", [])))
    
    print("\n--- Testing CLB ---")
    c = await clbphimxua_catalog_handler("movie", "clbphimxua_all")
    print("CLB catalog:", len(c.get("metas", [])))
    
    print("\n--- Testing Yanhh ---")
    y = await yanhh3d_catalog_handler("series", "yanhh3d_4k")
    print("Yanhh catalog:", len(y.get("metas", [])))

if __name__ == "__main__":
    asyncio.run(test_inspect())
