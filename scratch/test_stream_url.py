import urllib.request

url1 = 'https://embed.streamc.xyz/eyJoOiIzMGZhOWU3MmE5OWMxY2IzZGFiZGY4YTJlNDIyMjA2MSIsInQiOiI1YTNhZTA5YTdlZjBiMTZmMzRjMWE3YzJlNzAxNjI1ZGMyZDQwMjgzNjA5YjQwZGQwOTJmMWQ4MTFkMDI4YTNkIn0='
url2 = url1 + '?d=1'

for target_url in [url1, url2]:
    try:
        req = urllib.request.Request(target_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://embed.streamc.xyz/'
        })
        res = urllib.request.urlopen(req)
        print("URL:", target_url)
        print("Status:", res.status)
        print("Final URL:", res.url)
        content = res.read()
        print("Content-Type:", res.headers.get('Content-Type'))
        print("Content preview:", content[:500].decode('utf-8', errors='ignore'))
        print("=" * 60)
    except Exception as e:
        print("Error fetching", target_url, ":", e)
