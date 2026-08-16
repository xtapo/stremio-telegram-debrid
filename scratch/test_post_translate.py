import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import time
import httpx
from subtitles_service import parse_subtitles, rebuild_subtitles

async def translate_srt_fast(srt_content: str, target_lang: str = "vi") -> str:
    header, blocks = parse_subtitles(srt_content)
    if not blocks:
        return srt_content

    batch_size = 50
    chunks = [blocks[i:i+batch_size] for i in range(0, len(blocks), batch_size)]
    
    async def translate_chunk(chunk_blocks, client):
        lines_to_trans = [b["text"].replace("\n", " __NL__ ") for b in chunk_blocks]
        joined_text = "\n__SEP__\n".join(lines_to_trans)
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "dt": "t",
            "sl": "auto",
            "tl": target_lang
        }
        data = {
            "q": joined_text
        }
        try:
            resp = await client.post(url, params=params, data=data)
            if resp.status_code == 200:
                res_data = resp.json()
                translated_joined = "".join([item[0] for item in res_data[0] if item and item[0]])
                translated_lines = translated_joined.split("__SEP__")
                if len(translated_lines) == len(chunk_blocks):
                    for b, t in zip(chunk_blocks, translated_lines):
                        clean_t = t.replace("__NL__", "\n").replace("__nl__", "\n").strip()
                        b["text"] = clean_t
                    return
        except Exception as e:
            print("Batch error:", e)

    t0 = time.time()
    async with httpx.AsyncClient(timeout=15.0) as client:
        await asyncio.gather(*[translate_chunk(c, client) for c in chunks])
    t1 = time.time()
    print(f"Translated all {len(blocks)} subtitle lines in {t1 - t0:.2f} seconds!")
    
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
    print("\nSample translated Vietnamese VTT output:")
    print("\n".join(vi_vtt.split("\n")[:30]))

if __name__ == '__main__':
    asyncio.run(test())
