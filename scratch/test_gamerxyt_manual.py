import asyncio, httpx

async def run():
    pxl_api = 'https://pixeldrain.dev/api/file/u2xeUcL4'

    async with httpx.AsyncClient(headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36', 'Referer': 'https://pixeldrain.dev/'}) as client:
        r = await client.head(pxl_api, follow_redirects=True)
        print('Pxl API status:', r.status_code)
        if r.status_code == 200:
            print('Content-Type:', r.headers.get('content-type'))
            print('Content-Length:', r.headers.get('content-length'))

asyncio.run(run())
