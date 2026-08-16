import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import re
import httpx
import asyncio
from subtitles_service import parse_subtitles

async def test_numeric_tag():
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
    # Use [[[idx]]] which Google Translate leaves completely untouched
    tagged_lines = []
    for idx, b in enumerate(blocks):
        clean_text = b["text"].replace("\n", " ")
        tagged_lines.append(f"[[[{idx}]]] {clean_text}")
    joined_text = "\n".join(tagged_lines)
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "dt": "t", "sl": "auto", "tl": "vi"},
            data={"q": joined_text}
        )
        res_data = resp.json()
        translated_joined = "".join([item[0] for item in res_data[0] if item and item[0]])
        print("Raw translated joined text:\n", translated_joined)
        
        extracted = {}
        for m in re.finditer(r'\[\[\[\s*(\d+)\s*\]\]\]\s*([^\[]+)', translated_joined):
            i = int(m.group(1))
            t = m.group(2).strip()
            extracted[i] = t
            
        print("\nExtracted mapping:", extracted)
        for idx in range(len(blocks)):
            print(f"Block {idx}:", extracted.get(idx, "FALLBACK"))

if __name__ == '__main__':
    asyncio.run(test_numeric_tag())
