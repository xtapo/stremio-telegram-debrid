import urllib.request
import urllib.parse
import json

# Let's test making a request to streamc API if any, e.g., /api.php or similar, or inspect network requests
# Or let's test sending sub_json to embed.streamc.xyz endpoints
hash_id = '30fa9e72a99c1cb3dabdf8a2e4222061'

# Try POSTing hash or token to known stream endpoints
for ep in ['/api/stream', '/api.php', '/player/index.php', '/index.php', '/get_stream']:
    try:
        url = f'https://embed.streamc.xyz{ep}'
        req = urllib.request.Request(url, data=json.dumps({"hash": hash_id}).encode(), headers={'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json'})
        res = urllib.request.urlopen(req)
        print(f"EP {ep}: status {res.status}, body: {res.read()[:200]}")
    except Exception as e:
        print(f"EP {ep}: error {e}")
