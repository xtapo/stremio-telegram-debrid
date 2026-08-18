import httpx
import re

client = httpx.Client(headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://vidup.to/'}, timeout=15.0)

for url in [
    'https://ythd.org/embed/movie/19995',
    'https://ythd.org/embed/tv/33880/1/1',
    'https://ythd.org/embed/19995',
]:
    try:
        r = client.get(url)
        print(url, '-> Status:', r.status_code, 'Len:', len(r.text))
        print('Snippet:\n', r.text[:300])
    except Exception as e:
        print(url, '-> Error:', e)
