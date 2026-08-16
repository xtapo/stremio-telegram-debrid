import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import time
import httpx
import urllib.parse
import re
from subtitles_service import parse_subtitles, rebuild_subtitles

async def test_lingva_batch():
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
    
    lingva_instances = [
        "https://lingva.ml",
        "https://lingva.garudalinux.org",
        "https://translate.plausibility.cloud"
    ]
    
    t0 = time.time()
    for inst in lingva_instances:
        try:
            url = f"{inst}/api/v1/auto/vi/{urllib.parse.quote(joined_text)}"
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    translated_joined = resp.json().get("translation", "")
                    print("Lingva translated joined:\n", translated_joined)
                    for m in re.finditer(r'\[\s*\[\s*(\d+)\s*\]\s*\]\s*([^\[]+)', translated_joined):
                        i = int(m.group(1))
                        t = m.group(2).strip()
                        if i < len(blocks):
                            blocks[i]["text"] = t
                    vtt = rebuild_subtitles("WEBVTT\n\n", blocks)
                    print(f"\nFinal VTT ({time.time() - t0:.2f}s):\n{vtt}")
                    return
        except Exception as e:
            print(f"Lingva instance {inst} failed: {e}")

if __name__ == '__main__':
    asyncio.run(test_lingva_batch())
