import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import time
from config import Config
from subtitles_service import translate_gemini

async def test_gemini():
    Config.GEMINI_MODEL = "gemini-2.5-flash"
    test_srt = """1
00:04:09,708 --> 00:04:10,834
Kneel.

2
00:04:15,464 --> 00:04:17,506
I can make it clean, or...

3
00:04:17,507 --> 00:04:19,675
Might I at least know
the accusation, my prince?

4
00:04:19,676 --> 00:04:21,052
Where is he?

5
00:04:21,845 --> 00:04:23,637
- Who?
- My brother, the King.
"""
    print(f"Testing Gemini translation with model: {Config.GEMINI_MODEL}...")
    t0 = time.time()
    res = await translate_gemini(test_srt, Config.GEMINI_API_KEY, target_lang="vi")
    t1 = time.time()
    print(f"Translated in {t1 - t0:.2f}s:")
    print(res)

if __name__ == '__main__':
    asyncio.run(test_gemini())
