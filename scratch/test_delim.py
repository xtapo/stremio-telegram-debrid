import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import re
import httpx
import asyncio
from subtitles_service import parse_subtitles, rebuild_subtitles

async def test_batch():
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
"""
    _, blocks = parse_subtitles(test_srt)
    lines_to_trans = [b["text"].replace("\n", " __NL__ ") for b in blocks]
    joined_text = "\n__SEP__\n".join(lines_to_trans)
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "dt": "t", "sl": "auto", "tl": "vi"},
            data={"q": joined_text}
        )
        res_data = resp.json()
        translated_joined = "".join([item[0] for item in res_data[0] if item and item[0]])
        print("Raw translated joined text:\n", repr(translated_joined))
        
        parts = [p.strip() for p in re.split(r'__\s*sep\s*__', translated_joined, flags=re.IGNORECASE) if p.strip()]
        print("Split parts count:", len(parts), "Expected:", len(blocks))
        for p in parts:
            print(" ->", p.replace("__NL__", "\n").replace("__nl__", "\n"))

if __name__ == '__main__':
    asyncio.run(test_batch())
