import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import time
import re
from config import Config
from subtitles_service import parse_subtitles, rebuild_subtitles, translate_custom_ai

async def test_2_chunks():
    # 700 lines test
    raw_blocks = []
    for i in range(700):
        raw_blocks.append({
            "prefix": str(i+1),
            "time": f"00:{i//60:02d}:{i%60:02d},000 --> 00:{i//60:02d}:{i%60:02d},900",
            "text": f"This is line {i+1} of dialog."
        })
        
    chunk_size = 250
    chunks = [raw_blocks[i:i+chunk_size] for i in range(0, len(raw_blocks), chunk_size)]
    print(f"Translating {len(raw_blocks)} blocks in {len(chunks)} chunks of {chunk_size}...")
    
    async def translate_chunk(chunk_blocks, idx):
        raw_chunk_srt = "\n\n".join(f"{idx+1}\n{b['time']}\n{b['text']}" for idx, b in enumerate(chunk_blocks))
        res = await translate_custom_ai(raw_chunk_srt, target_lang="vi")
        if res.startswith("```"):
            res = re.sub(r"^```[a-zA-Z0-9]*\n", "", res)
            res = re.sub(r"\n```$", "", res)
        _, parsed = parse_subtitles(res.strip())
        if len(parsed) == len(chunk_blocks):
            for b_orig, b_trans in zip(chunk_blocks, parsed):
                b_orig["text"] = b_trans["text"].strip()
        elif parsed:
            for i, p in enumerate(parsed[:len(chunk_blocks)]):
                chunk_blocks[i]["text"] = p["text"].strip()
        print(f"Chunk {idx+1} parsed {len(parsed)}/{len(chunk_blocks)} lines.")

    t0 = time.time()
    await asyncio.gather(*[translate_chunk(c, i) for i, c in enumerate(chunks)])
    t1 = time.time()
    
    print(f"All 700 lines translated in {t1 - t0:.2f}s!")
    print("Sample lines 1-5:")
    for b in raw_blocks[:5]:
        print(f" - {b['time']}: {b['text']}")

if __name__ == '__main__':
    asyncio.run(test_2_chunks())
