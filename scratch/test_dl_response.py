import urllib.request
import httpx
import asyncio

async def test_dl():
    # Let's test the pixel URL and the workers.dev direct URL
    url_pixel = "https://pixel.hubcloud.cx/?id=d05c0846bbc635c6a573485cc65b523e7d032b2b4ceafae2f02af265caf264b1f99c77aff3537f3776a85ed1ba8d684ef1ebecf7b0aadf821de6fcda11e4828e2b6be5068eca34302366fa48b68af7f7580917bc8060080f8e1b8ce24e767ee4::a5e0c2a6abf0cc0a8948c9240e6873e2"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://gamerxyt.com/'
    }
    
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url_pixel, headers=headers)
        print("Final URL:", resp.url)
        print("Status code:", resp.status_code)
        print("Content-Type:", resp.headers.get('content-type'))
        print("Content-Length:", resp.headers.get('content-length'))
        print("Content sample (first 500 bytes):\n", resp.content[:500])

if __name__ == '__main__':
    asyncio.run(test_dl())
