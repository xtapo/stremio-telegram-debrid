import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import time
from config import Config
from subtitles_service import parse_subtitles, rebuild_subtitles, translate_custom_ai

async def test_parallel_custom_ai():
    # 700 lines test
    raw_blocks = []
    for i in range(700):
        raw_blocks.append({
            "prefix": str(i+1),
            "time": f"00:{i//60:02d}:{i%60:02d},000 --> 00:{i//60:02d}:{i%60:02d},900",
            "text": f"This is test dialogue sentence number {i+1} for our movie."
        })
        
    print(f"Testing parallel Custom AI translation on {len(raw_blocks)} blocks...")
    chunk_size = 100
    chunks = [raw_blocks[i:i+chunk_size] for i in range(0, len(raw_blocks), chunk_size)]
    
    async def translate_chunk(chunk_blocks, idx):
        t_start = time.time()
        raw_chunk_srt = "\n\n".join(f"{b['prefix']}\n{b['time']}\n{b['text']}" for b in chunk_blocks)
        res = await translate_custom_ai(raw_chunk_srt, target_lang="vi")
        print(f"Chunk {idx+1}/{len(chunks)} done in {time.time() - t_start:.2f}s (len={len(res)})")
        return res

    t0 = time.time()
    results = await asyncio.gather(*[translate_chunk(c, i) for i, c in enumerate(chunks)])
    t1 = time.time()
    print(f"\nALL 700 BLOCKS TRANSLATED PARALLEL IN: {t1 - t0:.2f} seconds!")

if __name__ == '__main__':
    asyncio.run(test_parallel_custom_ai())
