import asyncio
import httpx

async def check():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        # 1. Rido
        try:
            res1 = await client.get("https://ridomovies.su/api/search?q=avatar")
            print("Rido status:", res1.status_code, "text len:", len(res1.text))
            print("Rido json data:", res1.json().get("data", [])[:2])
        except Exception as e:
            print("Rido error:", e)

        # 2. CLB
        try:
            res2 = await client.get("https://clbphimxua.com/wp-json/wp/v2/posts?per_page=5&_embed")
            print("CLB status:", res2.status_code, "len:", len(res2.text))
            if res2.status_code == 200:
                print("CLB type:", type(res2.json()), "count:", len(res2.json()) if isinstance(res2.json(), list) else "not list")
        except Exception as e:
            print("CLB error:", e)

        # 3. Yanhh
        try:
            res3 = await client.get("https://yanhh3d.run/hoat-hinh-4k?page=1")
            print("Yanhh status:", res3.status_code, "len:", len(res3.text))
            import re
            links = re.findall(r'<a[^>]+href=["\'](/[^"\']+)["\']', res3.text)
            print("Yanhh sample links:", links[:10])
        except Exception as e:
            print("Yanhh error:", e)

if __name__ == "__main__":
    asyncio.run(check())
