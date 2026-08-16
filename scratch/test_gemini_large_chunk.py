import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import time
from config import Config
from subtitles_service import extract_embedded_subtitle, translate_gemini, parse_subtitles, rebuild_subtitles

async def test_single_call_gemini():
    video_url = "https://9f7e2b9f5ee304d858c9a743a3aa5357.r2.cloudflarestorage.com/hub2/a910ecf689f8a86c96adc2a803abca0d?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=f3a2fc8098af833664a1af1908249931%2F20260816%2Fauto%2Fs3%2Faws4_request&X-Amz-Date=20260816T005902Z&X-Amz-Expires=28800&X-Amz-SignedHeaders=host&response-content-disposition=attachment%3B%20filename%3D%22House.of.the.Dragon.S03E01.480p.WEB-DL.Hindi-English.ESub.x264-MoviesDrives.CV.mkv%22&X-Amz-Signature=b09c8e2a96321e306a8df9bd90c22b7674b4227118a25b88790021a688ec87a4"
    
    print("Extracting embedded subtitle...")
    srt = await extract_embedded_subtitle(video_url)
    if not srt:
        print("No srt extracted.")
        return
        
    _, blocks = parse_subtitles(srt)
    print(f"Total blocks: {len(blocks)}")
    
    # Send chunks of 250 blocks (only 2 requests total!)
    chunk_size = 250
    chunks = [blocks[i:i+chunk_size] for i in range(0, len(blocks), chunk_size)]
    print(f"Number of chunks: {len(chunks)}")
    
    t0 = time.time()
    for idx, c in enumerate(chunks):
        print(f"Translating chunk {idx+1}/{len(chunks)} ({len(c)} lines)...")
        raw_chunk_srt = "\n\n".join(f"{b['prefix'] or i+1}\n{b['time']}\n{b['text']}" for i, b in enumerate(c))
        res = await translate_gemini(raw_chunk_srt, Config.GEMINI_API_KEY, target_lang="vi")
        print(f"Chunk {idx+1} result length: {len(res)} bytes")
        # Sleep 1s between chunks to be 100% compliant with free tier
        if idx < len(chunks) - 1:
            await asyncio.sleep(1.5)
            
    t1 = time.time()
    print(f"All chunks translated in {t1 - t0:.2f}s!")

if __name__ == '__main__':
    asyncio.run(test_single_call_gemini())
