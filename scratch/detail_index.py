import httpx
import re

client = httpx.Client(
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
    timeout=15.0
)

r = client.get('https://www.vidking.net/assets/index-_AMw2RSV.js')
text = r.text
print("index-_AMw2RSV.js len:", len(text))

# Let's find all URLs or paths
urls = re.findall(r'["\'](https?://[^"\']+|/[^"\']+)["\']', text)
for u in set(urls):
    if not u.startswith('/assets') and not u.startswith('http://www.w3.org'):
        print("URL/Path:", u)

# Let's search for functions that make requests or handle routes
# Let's print sections mentioning embed or tmdb
for m in re.finditer(r'(?:movie|tv|tmdb|stream|player|source|hls|m3u8)', text, re.IGNORECASE):
    idx = m.start()
    snippet = text[max(0, idx-100):min(len(text), idx+200)]
    print("\n--- SNIPPET ---")
    print(snippet)
