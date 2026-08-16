import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import time
from config import Config
from subtitles_service import translate_srt_fast_batch

async def test_direct_gemini():
    sample_srt = """1
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

6
00:04:23,638 --> 00:04:24,931
In his quarters!

7
00:04:26,099 --> 00:04:28,350
You are a traitor to the crown.
"""
    print(f"Testing translate_srt_fast_batch with Gemini ({Config.GEMINI_MODEL})...")
    t0 = time.time()
    vtt = await translate_srt_fast_batch(sample_srt, target_lang="vi")
    t1 = time.time()
    print(f"Translated successfully in {t1 - t0:.2f}s:")
    print(vtt)

if __name__ == '__main__':
    asyncio.run(test_direct_gemini())
