import httpx
import re

client = httpx.Client(
    headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://www.vidking.net/',
    },
    follow_redirects=True,
    timeout=15.0
)

js_files = [
    '/assets/index-_AMw2RSV.js',
    '/assets/react-core-Dom31imV.js',
    '/assets/data-libs-DyAZjcUE.js',
    '/assets/ui-libs-DfEg2YJ5.js',
    '/assets/react-router-VS2nkS8h.js'
]

for js_path in js_files:
    url = f"https://www.vidking.net{js_path}"
    try:
        r = client.get(url)
        content = r.text
        print(f"\n--- {js_path} (len: {len(content)}) ---")
        
        # Search for api calls, fetch, axios, endpoints
        api_endpoints = re.findall(r'["\'](/api/[^"\']+|https?://[^"\']+)["\']', content)
        print("Endpoints/URLs:", set(api_endpoints))
        
        # Search for occurrences of tmdb or stream or m3u8 or video
        for match in re.finditer(r'(?:fetch|axios|get|post)\s*\([^\)]+\)', content):
            snippet = match.group(0)
            if any(k in snippet.lower() for k in ['api', 'embed', 'stream', 'source', 'movie', 'tv', 'vidking']):
                print("Call snippet:", snippet[:200])
                
        # Also look for string templates like `${
        templates = re.findall(r'`[^`]*?(?:api|stream|source|embed|tmdb)[^`]*?`', content)
        for t in templates[:10]:
            print("Template string:", t)
    except Exception as e:
        print(f"Error {js_path}:", e)
