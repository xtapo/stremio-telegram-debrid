import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
from config import Config
from subtitles_service import translate_srt_fast_batch

async def test_full_pipeline():
    sample_srt = """1
00:04:09,708 --> 00:04:10,834
Kneel.

2
00:04:15,464 --> 00:04:17,506
I can make it clean, or...

3
00:04:17,507 --> 00:04:19,675
Might I at least know the accusation, my prince?
"""
    print(f"Translating sample with Configured AI stack (Gemini model: {Config.GEMINI_MODEL}, Custom AI: {Config.CUSTOM_AI_MODEL})...")
    vtt = await translate_srt_fast_batch(sample_srt, target_lang="vi")
    print("VTT Result:")
    print(vtt)

if __name__ == '__main__':
    asyncio.run(test_full_pipeline())
