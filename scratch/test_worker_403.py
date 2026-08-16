import httpx
import asyncio

async def test_worker_link():
    url = "https://spring-tree-7af2.genet319598570.workers.dev/4e9d4f459e75dff32438ebc9889b3966ab251cd80eceec8ead367b89994f6acb826b32c00655fc7b4b3d42eedde6f724::f69bea7763f0ca70f4ff89506036abf3/1397996304/[Moviesdrives.com]-House.Of.The.Dragon.S02E02.MULTi.2160p.JIO.WEB-DL.AAC2.0.H.264-[moviesdrives.com].mkv"
    
    # 1. No Referer
    print("1. Testing No Referer:")
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        r1 = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Range": "bytes=0-1000"})
        print("Status:", r1.status_code)
        print("Headers:", r1.headers)
        
    # 2. With Referer: gamerxyt.com
    print("\n2. Testing With Referer gamerxyt.com:")
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        r2 = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://gamerxyt.com/", "Range": "bytes=0-1000"})
        print("Status:", r2.status_code)
        
    # 3. With Referer: hubcloud.cx
    print("\n3. Testing With Referer hubcloud.cx:")
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        r3 = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://hubcloud.cx/", "Range": "bytes=0-1000"})
        print("Status:", r3.status_code)

if __name__ == '__main__':
    asyncio.run(test_worker_link())
