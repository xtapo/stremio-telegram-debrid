import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import time
import httpx
import urllib.parse
from subtitles_service import parse_subtitles, rebuild_subtitles

async def translate_srt_fast(srt_content: str, target_lang: str = "vi") -> str:
    header, blocks = parse_subtitles(srt_content)
    if not blocks:
        return srt_content

    batch_size = 40
    chunks = [blocks[i:i+batch_size] for i in range(0, len(blocks), batch_size)]
    
    async def translate_chunk(chunk_blocks):
        lines_to_trans = [b["text"].replace("\n", " [NL] ") for b in chunk_blocks]
        joined_text = "\n[SEP]\n".join(lines_to_trans)
        try:
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&dt=t&sl=auto&tl={target_lang}&q={urllib.parse.quote(joined_text)}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    translated_joined = "".join([item[0] for item in data[0] if item[0]])
                    translated_lines = translated_joined.split("[SEP]")
                    if len(translated_lines) == len(chunk_blocks):
                        for b, t in zip(chunk_blocks, translated_lines):
                            clean_t = t.replace("[NL]", "\n").replace("[nl]", "\n").strip()
                            b["text"] = clean_t
                        return
        except Exception as e:
            print("Batch error:", e)
            
        # Fallback individual
        async with httpx.AsyncClient(timeout=5.0) as client:
            for b in chunk_blocks:
                try:
                    u = f"https://translate.googleapis.com/translate_a/single?client=gtx&dt=t&sl=auto&tl={target_lang}&q={urllib.parse.quote(b['text'])}"
                    r = await client.get(u)
                    if r.status_code == 200:
                        b["text"] = "".join([item[0] for item in r.json()[0] if item[0]])
                except Exception:
                    pass

    t0 = time.time()
    await asyncio.gather(*[translate_chunk(c) for c in chunks])
    t1 = time.time()
    print(f"Translated {len(blocks)} subtitle lines in {t1 - t0:.2f} seconds!")
    
    vtt_header = "WEBVTT\n\n"
    return rebuild_subtitles(vtt_header, blocks)

async def test():
    # Fetch an actual English subtitle from OpenSubtitles for House of the Dragon S1E1
    url = "https://subs5.strem.io/en/download/subencoding-stremio-utf8/src-api/file/1962471920"
    print("Downloading sample English subtitle...")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        srt_raw = resp.text
        
    print(f"Downloaded {len(srt_raw)} bytes of English subtitle.")
    vi_vtt = await translate_srt_fast(srt_raw)
    print("Sample translated VTT output:")
    print("\n".join(vi_vtt.split("\n")[:25]))

if __name__ == '__main__':
    asyncio.run(test())
