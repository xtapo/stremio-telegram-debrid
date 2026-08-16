import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import time
import re
import httpx
import urllib.parse
from subtitles_service import parse_subtitles, rebuild_subtitles

async def test_get_batch():
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
    tagged_lines = []
    for idx, b in enumerate(blocks):
        clean_text = b["text"].replace("\n", " ")
        tagged_lines.append(f"[[{idx}]] {clean_text}")
    joined_text = "\n".join(tagged_lines)
    
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&dt=t&sl=auto&tl=vi&q={urllib.parse.quote(joined_text)}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        print("Status:", resp.status_code)
        if resp.status_code == 200:
            res_data = resp.json()
            translated_joined = "".join([item[0] for item in res_data[0] if item and item[0]])
            print("Translated Joined:\n", translated_joined)
            for m in re.finditer(r'\[\s*\[\s*(\d+)\s*\]\s*\]\s*([^\[]+)', translated_joined):
                i = int(m.group(1))
                t = m.group(2).strip()
                if i < len(blocks):
                    blocks[i]["text"] = t
                    
    vtt = rebuild_subtitles("WEBVTT\n\n", blocks)
    print("\nResult VTT:\n", vtt)

if __name__ == '__main__':
    asyncio.run(test_get_batch())
