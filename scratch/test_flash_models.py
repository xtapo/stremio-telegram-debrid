import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
from config import Config
from subtitles_service import translate_gemini

async def test_flash_latest():
    test_srt = "1\n00:01:00,000 --> 00:01:05,000\nHello, my friend! How are you today?"
    for m in ["gemini-flash-latest", "gemini-3.5-flash", "gemini-3.1-flash-lite"]:
        try:
            Config.GEMINI_MODEL = m
            res = await translate_gemini(test_srt, Config.GEMINI_API_KEY, target_lang="vi")
            print(f"Model {m} SUCCESS:\n", res)
            break
        except Exception as e:
            print(f"Model {m} error:", e)

if __name__ == '__main__':
    asyncio.run(test_flash_latest())
