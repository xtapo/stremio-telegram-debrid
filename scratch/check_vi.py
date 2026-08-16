import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import httpx

async def check_vi_subs():
    url = f"https://opensubtitles-v3.strem.io/subtitles/movie/tt32890033.json"
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get(url)
        subs = resp.json().get("subtitles", [])
        langs = set(s.get("lang") for s in subs)
        print("Languages available in OpenSubtitles v3 for Minions & Monsters:", langs)
        vi_subs = [s for s in subs if s.get("lang") in ("vie", "vi", "vie-vie")]
        print(f"Found {len(vi_subs)} Vietnamese subtitles!")
        for v in vi_subs:
            print(" -", v)

if __name__ == '__main__':
    asyncio.run(check_vi_subs())
