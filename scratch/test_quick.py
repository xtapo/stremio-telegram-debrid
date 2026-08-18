import httpx

client = httpx.Client(
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.vidking.net/",
        "Origin": "https://www.vidking.net"
    },
    timeout=httpx.Timeout(5.0, connect=3.0)
)

print("Fetching seed...", flush=True)
try:
    r = client.get("https://api.speedracelight.com/seed?mediaId=550")
    print("Seed status:", r.status_code, r.text, flush=True)
except Exception as e:
    print("Seed error:", e, flush=True)

print("Fetching TMDB meta...", flush=True)
try:
    r = client.get("https://db.speedracelight.com/3/movie/550?append_to_response=external_ids")
    print("Meta status:", r.status_code, r.text[:200], flush=True)
except Exception as e:
    print("Meta error:", e, flush=True)
