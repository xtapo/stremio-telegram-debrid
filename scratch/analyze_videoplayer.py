import httpx
import re

client = httpx.Client(
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
    timeout=15.0
)

r = client.get('https://www.vidking.net/assets/VideoPlayer-D5eTfQPp.js')
text = r.text
print("VideoPlayer-D5eTfQPp.js len:", len(text))

# Let's find all URLs, endpoints, keys, APIs
urls = re.findall(r'["\'](https?://[^"\']+|/[^"\']+)["\']', text)
for u in set(urls):
    if not u.startswith('/assets') and not u.startswith('http://www.w3.org'):
        print("URL/Path:", u)

# Let's search for fetch / api calls / server endpoints
for m in re.finditer(r'(?:fetch|axios|\.get|\.post|endpoint|api|stream|source|m3u8|token|decrypt)', text, re.IGNORECASE):
    idx = m.start()
    snippet = text[max(0, idx-50):min(len(text), idx+150)]
    print("\n--- SNIPPET ---")
    print(snippet)
