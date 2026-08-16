import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
from subtitles_service import extract_embedded_subtitle, translate_srt_fast_batch

async def test_extract_video():
    # Minions and Monsters R2 video url
    video_url = "https://da194e3e41011e58ea95b0914c6212d3.r2.cloudflarestorage.com/hub/dedf2a9075eefac1a0c972d2e4d0d2f0?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=96b5033bc905597cdb60f74329e90e32%2F20260816%2Fauto%2Fs3%2Faws4_request&X-Amz-Date=20260816T003923Z&X-Amz-Expires=28800&X-Amz-SignedHeaders=host&response-content-disposition=attachment%3B%20filename%3D%22Minions.and.Monsters.2026.480p.WEB-DL.Hindi-English.ESub.x264-MoviesDrives.mov.mkv%22&X-Amz-Signature=716f19a7402975e8af35ed19b0bd77ed98ada0309e0196af89e742f4342aaa29"
    
    print(f"Extracting embedded subtitle from video URL...")
    srt = await extract_embedded_subtitle(video_url)
    if srt:
        print(f"Extracted {len(srt)} bytes of EMBEDDED subtitle!")
        print("First 10 lines of embedded subtitle:")
        print("\n".join(srt.splitlines()[:10]))
        
        print("\nTranslating embedded subtitle to Vietnamese...")
        vi_vtt = await translate_srt_fast_batch(srt)
        print("First 15 lines of translated Vietnamese VTT:")
        print("\n".join(vi_vtt.splitlines()[:15]))
    else:
        print("No embedded subtitle extracted or ffprobe/ffmpeg not in PATH.")

if __name__ == '__main__':
    asyncio.run(test_extract_video())
