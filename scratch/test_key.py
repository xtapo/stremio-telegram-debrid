import httpx

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://vixsrc.to/'
}
client = httpx.Client(headers=headers, timeout=15.0, follow_redirects=True)
r = client.get('https://vixsrc.to/storage/enc.key')
print('Key status:', r.status_code, 'Key length:', len(r.content))
