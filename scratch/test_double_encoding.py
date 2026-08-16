import httpx
import asyncio
import urllib.parse

async def test_double_encoding():
    # Double encoded URL with %3A%3A:
    url_bad = "https://spring-tree-7af2.genet319598570.workers.dev/4e9d4f459e75dff32438ebc9889b3966ab251cd80eceec8ead367b89994f6acb826b32c00655fc7b4b3d42eedde6f724%3A%3Af69bea7763f0ca70f4ff89506036abf3/1397996304/[Moviesdrives.com]-House.Of.The.Dragon.S02E02.MULTi.2160p.JIO.WEB-DL.AAC2.0.H.264-[moviesdrives.com].mkv"
    # Unquoted literal ::
    url_good = "https://spring-tree-7af2.genet319598570.workers.dev/4e9d4f459e75dff32438ebc9889b3966ab251cd80eceec8ead367b89994f6acb826b32c00655fc7b4b3d42eedde6f724::f69bea7763f0ca70f4ff89506036abf3/1397996304/[Moviesdrives.com]-House.Of.The.Dragon.S02E02.MULTi.2160p.JIO.WEB-DL.AAC2.0.H.264-[moviesdrives.com].mkv"
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        r_bad = await client.get(url_bad, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-10"})
        print("URL with %3A%3A status:", r_bad.status_code)
        
        r_good = await client.get(url_good, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-10"})
        print("URL with literal :: status:", r_good.status_code)

if __name__ == '__main__':
    asyncio.run(test_double_encoding())
