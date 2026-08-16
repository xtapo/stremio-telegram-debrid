import httpx
import asyncio

async def test_playable_streams():
    # 1. Test Cloudflare R2 link
    r2_url = "https://36ca20d938d7985a0c3646e8dd103d92.r2.cloudflarestorage.com/hub2/d275c23cb3eafe9cc2252b5084aad26a?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=0464a11272e5a07abcce337fd0b60cc8%2F20260816%2Fauto%2Fs3%2Faws4_request&X-Amz-Date=20260816T002620Z&X-Amz-Expires=28800&X-Amz-SignedHeaders=host&response-content-disposition=attachment%3B%20filename%3D%22Spooky.in.Love.S01E01.Episode.1.1080p.NF.WEB-DL.MULTi.AAC.2.0.H264-MoviesDrives.CV.mkv%22&X-Amz-Signature=a9e562d34b439651e77e65cc9eb4d6c41912da46548e59bc79807140b0259416"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Range': 'bytes=0-1000'
    }
    
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(r2_url, headers=headers)
        print("R2 Status:", resp.status_code)
        print("R2 Content-Type:", resp.headers.get('content-type'))
        print("R2 Content-Range:", resp.headers.get('content-range'))
        print("R2 First 16 bytes:", resp.content[:16].hex())
        # Check MKV magic header: 1a45dfa3
        if resp.content.startswith(b"\x1a\x45\xdf\xa3"):
            print(">>> VERIFIED: 100% REAL MKV VIDEO FILE! <<<")

if __name__ == '__main__':
    asyncio.run(test_playable_streams())
