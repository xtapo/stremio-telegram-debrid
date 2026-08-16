import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import time
import httpx
import urllib.parse
import re

async def test_fast_lingva():
    # 700 lines
    sample_lines = [f"This is dialogue line number {i+1} spoken by character." for i in range(700)]
    
    batch_size = 180
    chunks = [sample_lines[i:i+batch_size] for i in range(0, len(sample_lines), batch_size)]
    print(f"Total lines: {len(sample_lines)} divided into {len(chunks)} chunks of {batch_size}...")
    
    async def translate_chunk(lines, idx, client):
        t0 = time.time()
        tagged = [f"[[{i}]] {l}" for i, l in enumerate(lines)]
        joined = "\n".join(tagged)
        url = f"https://lingva.ml/api/v1/auto/vi/{urllib.parse.quote(joined)}"
        resp = await client.get(url)
        print(f"Chunk {idx+1}/{len(chunks)} done in {time.time() - t0:.2f}s (status: {resp.status_code})")
        return resp.json().get("translation", "")

    t_all = time.time()
    async with httpx.AsyncClient(timeout=8.0) as client:
        res = await asyncio.gather(*[translate_chunk(c, i, client) for i, c in enumerate(chunks)])
    print(f"\nALL 700 LINES TRANSLATED IN {time.time() - t_all:.2f} SECONDS!")

if __name__ == '__main__':
    asyncio.run(test_fast_lingva())
