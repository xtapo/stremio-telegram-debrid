import asyncio
import sys
import httpx

sys.stdout.reconfigure(encoding='utf-8')

async def fetch_catalog_items(base_endpoint: str, skip: int, limit: int = 30) -> list:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    target_start = skip
    target_end = skip + limit
    
    delim = "&" if "?" in base_endpoint else "?"
    
    async with httpx.AsyncClient(headers=headers, timeout=10.0, follow_redirects=True) as client:
        # Fetch page 1 first to read actual per_page from meta
        res1 = await client.get(f"{base_endpoint}{delim}page=1")
        if res1.status_code != 200:
            return []
        
        body1 = res1.json()
        meta = body1.get("meta", {})
        per_page = meta.get("per_page", 20) or 20
        total = meta.get("total", 0)
        
        print(f"Endpoint: {base_endpoint} | API per_page: {per_page} | Total items: {total}")
        
        if total > 0 and target_start >= total:
            return []
            
        start_page = (target_start // per_page) + 1
        end_page = ((target_end - 1) // per_page) + 1
        
        offset_in_concatenated = target_start % per_page
        
        accumulated_items = []
        for p in range(start_page, end_page + 1):
            if p == 1:
                items = body1.get("data", [])
            else:
                rp = await client.get(f"{base_endpoint}{delim}page={p}")
                items = rp.json().get("data", []) if rp.status_code == 200 else []
                
            accumulated_items.extend(items)
            if len(items) < per_page:
                break
                
        sliced = accumulated_items[offset_in_concatenated : offset_in_concatenated + limit]
        return sliced

async def main():
    # Test Genre Hentai (NqlIpFB5ov) at skips 0, 20, 40, 60, 100
    genre_endpoint = "https://topxx.vip/api/v1/genres/NqlIpFB5ov/movies"
    for skip in [0, 20, 40, 60, 100]:
        items = await fetch_catalog_items(genre_endpoint, skip=skip)
        print(f"Genre skip={skip:3d}: Fetched {len(items)} items. First title: {items[0]['trans'][0]['title'] if items else 'NONE'}")

    print("\n" + "="*50 + "\n")
    # Test Country Japan (jp) at skips 0, 20, 40, 60, 100
    country_endpoint = "https://topxx.vip/api/v1/countries/jp/movies"
    for skip in [0, 20, 40, 60, 100]:
        items = await fetch_catalog_items(country_endpoint, skip=skip)
        print(f"Country skip={skip:3d}: Fetched {len(items)} items. First title: {items[0]['trans'][0]['title'] if items else 'NONE'}")

if __name__ == "__main__":
    asyncio.run(main())
