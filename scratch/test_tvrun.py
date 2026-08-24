import httpx

async def main():
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}, timeout=15.0) as client:
        js_resp = await client.get("https://tvrun.online/static/js/main.7210f9c8.js")
        text = js_resp.text
        
        idx = text.find("https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8")
        if idx != -1:
            print("=== Parsing snippet ===")
            print(text[idx-500:idx+2500])

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
