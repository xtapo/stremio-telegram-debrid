import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import time
import re
import httpx
from subtitles_service import parse_subtitles, rebuild_subtitles

async def test_fast_google_batch():
    # 700 lines test
    raw_blocks = []
    for i in range(700):
        raw_blocks.append({
            "prefix": str(i+1),
            "time": f"00:{i//60:02d}:{i%60:02d},000 --> 00:{i//60:02d}:{i%60:02d},900",
            "text": f"This is test dialogue sentence number {i+1} for our movie."
        })
        
    print(f"Testing Ultra-Fast Google Translate Batch on {len(raw_blocks)} blocks...")
    batch_size = 50
    chunks = [raw_blocks[i:i+batch_size] for i in range(0, len(raw_blocks), batch_size)]
    
    async def translate_chunk(chunk_blocks, client):
        tagged_lines = []
        for idx, b in enumerate(chunk_blocks):
            clean_text = b["text"].replace("\n", " ")
            tagged_lines.append(f"[[[{idx}]]] {clean_text}")
        joined_text = "\n".join(tagged_lines)
        
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "dt": "t",
            "sl": "auto",
            "tl": "vi"
        }
        data = {"q": joined_text}
        resp = await client.post(url, params=params, data=data)
        if resp.status_code == 200:
            res_data = resp.json()
            translated_joined = "".join([item[0] for item in res_data[0] if item and item[0]])
            extracted = {}
            for m in re.finditer(r'\[\[\[\s*(\d+)\s*\]\]\]\s*([^\[]+)', translated_joined):
                i = int(m.group(1))
                t = m.group(2).strip()
                extracted[i] = t
            for idx, b in enumerate(chunk_blocks):
                if idx in extracted:
                    b["text"] = extracted[idx]

    t0 = time.time()
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        await asyncio.gather(*[translate_chunk(c, client) for c in chunks])
    t1 = time.time()
    
    print(f"ALL 700 BLOCKS TRANSLATED IN: {t1 - t0:.2f} SECONDS!")
    print("Sample translated line:", raw_blocks[0]["text"])

if __name__ == '__main__':
    asyncio.run(test_fast_google_batch())
