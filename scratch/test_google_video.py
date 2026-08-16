import httpx
import asyncio

async def test_google_video():
    url = "https://video-downloads.googleusercontent.com/ADGPM2micSXWAFGvwavGPfnBx3MtSv1JDFIs3fKRN4y1dQCoiytss_aS9gia_t_yGQbR-8yYnAhgUpfpIcuWSaADYBRNcoLUMFi3KPyUj5jXGQ9e3nszZgJTsKE2VuGufV2Nl4Yhk6Phy6wH61-BOrnSQ4xuBQNLT_0V3O5nVaMV0kzpSQwJgKGIqf6xTibvGwDFp4A4u5bGQkbkBTihDYCFbG_pFXFaKEbaLyiTbX8KkCwPv8Gk-s_A6A8pCUK0MM0OHbYvDAcz"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Range': 'bytes=0-1024'
    }
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        print("Status code:", resp.status_code)
        print("Content-Type:", resp.headers.get('content-type'))
        print("Content-Length:", resp.headers.get('content-length'))
        print("Content-Range:", resp.headers.get('content-range'))
        print("First 16 bytes (hex):", resp.content[:16].hex())
        # Matroska / MKV magic bytes start with 1a45dfa3
        if resp.content.startswith(b"\x1a\x45\xdf\xa3") or b"matroska" in resp.content[:100] or resp.content.startswith(b"\x00\x00\x00"):
            print("VALID BINARY VIDEO STREAM FOUND!")

if __name__ == '__main__':
    asyncio.run(test_google_video())
