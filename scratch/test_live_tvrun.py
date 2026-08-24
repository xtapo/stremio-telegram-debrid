import httpx
import asyncio

async def main():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get("http://127.0.0.1:7860/tvrun/tv")
            print("Status:", r.status_code)
            print("Content length:", len(r.text))
            
            # test countries api
            r2 = await client.get("http://127.0.0.1:7860/tvrun/api/countries")
            print("API countries status:", r2.status_code, "len:", len(r2.text))
            
            # test channels api
            r3 = await client.get("http://127.0.0.1:7860/tvrun/api/channels?source=vn")
            print("API channels status:", r3.status_code, "total channels in json:", len(r3.json().get("channels", [])))
            
            # test streams for a channel
            channels = r3.json().get("channels", [])
            if channels:
                print("First channel stream test:")
                print("Name:", channels[0]["title"])
                print("URL:", channels[0]["url"])
                try:
                    stream_r = await client.get(channels[0]["url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=5.0)
                    print("Stream reachable status:", stream_r.status_code)
                except Exception as e:
                    print("Stream reachable error:", e)
    except Exception as e:
        print("Localhost error:", e)

if __name__ == "__main__":
    asyncio.run(main())
