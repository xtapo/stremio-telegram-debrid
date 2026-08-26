import asyncio
import httpx
from addon import app

async def test_full_server():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:7860") as client:
        print("=== 1. Checking Addons List from Dashboard ===")
        r = await client.get("/api/system/addons")
        print("Addons endpoint status:", r.status_code)
        addons = r.json().get("addons", [])
        print(f"Total active addons: {len(addons)}")
        for a in addons:
            print(f"  [{a.get('id')}] {a.get('name')}")

        print("\n=== 2. Checking Search across all sources ===")
        r_search = await client.get("/api/search?q=conan")
        print("Search status:", r_search.status_code)
        search_data = r_search.json()
        print(f"Total unified search results for 'conan': {search_data.get('total')}")
        for it in search_data.get("results", [])[:6]:
            print(f"  - [{it.get('source')}] {it.get('title')} ({it.get('year')})")

        print("\n=== 3. Checking Media Details for KKPhim ===")
        r_det = await client.get("/api/media/details?source=kkphim&id=tham-tu-lung-danh-conan")
        print("KKPhim detail status:", r_det.status_code)
        det_data = r_det.json()
        print(f"Title: {det_data.get('title')}, Episodes count: {len(det_data.get('episodes', []))}")

        print("\n=== 4. Checking Main Addon Manifests ===")
        for route in [
            "/kkphim/manifest.json",
            "/ridomovies/manifest.json",
            "/yanhh3d/manifest.json",
            "/nguonc/manifest.json",
            "/vsmov/manifest.json"
        ]:
            r_m = await client.get(route)
            print(f"  {route} -> status {r_m.status_code}, name: {r_m.json().get('name')}")

if __name__ == "__main__":
    asyncio.run(test_full_server())
