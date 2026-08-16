import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import time
import re
import httpx
from subtitles_service import parse_subtitles, rebuild_subtitles

async def test_robust_google_batch():
    test_srt = """1
00:04:09,708 --> 00:04:10,834
Kneel.

2
00:04:15,464 --> 00:04:17,506
I can make it clean, or...

3
00:04:17,507 --> 00:04:19,675
Might I at least know the accusation, my prince?

4
00:04:19,676 --> 00:04:21,052
Where is he?

5
00:04:21,845 --> 00:04:23,637
- Who?
- My brother, the king.
"""
    _, blocks = parse_subtitles(test_srt)
    batch_size = 50
    chunks = [blocks[i:i+batch_size] for i in range(0, len(blocks), batch_size)]
    
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
            print("Raw response from Google:", translated_joined)
            extracted = {}
            for m in re.finditer(r'\[\s*\[\s*\[\s*(\d+)\s*\]\s*\]\s*\]\s*([^\[]+)', translated_joined):
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
    
    vtt = rebuild_subtitles("WEBVTT\n\n", blocks)
    print(f"\nTranslated in {t1 - t0:.2f}s:\n{vtt}")

if __name__ == '__main__':
    asyncio.run(test_robust_google_batch())
