import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import time
from config import Config
from subtitles_service import translate_gemini, translate_custom_ai

async def test_models():
    test_srt = "1\n00:01:00,000 --> 00:01:05,000\nHello, my friend! How are you today?"
    
    # 1. Test gemini-2.5-flash-lite
    print("Testing gemini-2.5-flash-lite...")
    try:
        Config.GEMINI_MODEL = "gemini-2.5-flash-lite"
        res = await translate_gemini(test_srt, Config.GEMINI_API_KEY, target_lang="vi")
        print("Gemini-2.5-flash-lite success:\n", res)
    except Exception as e:
        print("Gemini-2.5-flash-lite error:", e)

    # 2. Test Custom AI
    print("\nTesting Custom AI (https://ai.xtapo.org/v1)...")
    try:
        res2 = await translate_custom_ai(test_srt, target_lang="vi")
        print("Custom AI success:\n", res2)
    except Exception as e:
        print("Custom AI error:", e)

if __name__ == '__main__':
    asyncio.run(test_models())
