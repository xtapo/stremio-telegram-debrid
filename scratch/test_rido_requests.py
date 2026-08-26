import requests
import asyncio

rido_session = requests.Session()
rido_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://ridomovies.su/",
    "Origin": "https://ridomovies.su"
}
rido_session.headers.update(rido_headers)

async def fetch_rido_async(url: str):
    def _do_get():
        return rido_session.get(url, timeout=10)
    res = await asyncio.to_thread(_do_get)
    print("Status:", res.status_code)
    if res.status_code == 200:
        print("Data len:", len(res.json().get('data', [])))

asyncio.run(fetch_rido_async("https://ridomovies.su/api/search?q=avatar"))
