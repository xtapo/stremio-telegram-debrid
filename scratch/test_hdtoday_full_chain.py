import httpx
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://hdtoday.sc/'
}
client = httpx.Client(headers=headers, timeout=15.0, follow_redirects=True)

r = client.get('https://vixsrc.to/api/movie/82023')
src_path = r.json().get('src')
embed_url = 'https://vixsrc.to' + src_path
r_embed = client.get(embed_url, headers={'Referer': 'https://vixsrc.to/movie/82023'})

token = re.search(r"['\"]token['\"]\s*:\s*['\"]([^'\"]+)['\"]", r_embed.text).group(1)
expires = re.search(r"['\"]expires['\"]\s*:\s*['\"]([^'\"]+)['\"]", r_embed.text).group(1)
pl_base = re.search(r"url:\s*['\"](https://[^'\"]+)['\"]", r_embed.text).group(1)

master_url = f"{pl_base}?token={token}&expires={expires}&h=1&lang=en"
r_master = client.get(master_url, headers={'Referer': embed_url, 'Origin': 'https://vixsrc.to'})

for line in r_master.text.splitlines():
    if not line.startswith('#') and line.strip():
        video_url = line.strip()
        print('Fetching video playlist:', video_url)
        r_v = client.get(video_url, headers={'Referer': embed_url, 'Origin': 'https://vixsrc.to'})
        print('Video playlist text:\n', r_v.text[:400])
        
        # Test fetching a segment
        for v_line in r_v.text.splitlines():
            if not v_line.startswith('#') and v_line.strip():
                ts_url = v_line.strip()
                print('\nFetching TS chunk:', ts_url)
                r_ts = client.get(ts_url, headers={'Referer': embed_url, 'Origin': 'https://vixsrc.to'})
                print('TS Chunk status:', r_ts.status_code, 'Bytes:', len(r_ts.content))
                break
        break
