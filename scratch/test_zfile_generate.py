import asyncio
import httpx
import re

url_zfile = 'https://driveseed.org/zfile/vMHFjZm67Ve6pRIHLnpZ'

async def test():
    client = httpx.AsyncClient(headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, follow_redirects=True, timeout=20)
    r2 = await client.get(url_zfile)
    key_match = re.search(r'formData\.append\(\s*[\'"]key[\'"]\s*,\s*[\'"]([^\'"]+)[\'"]', r2.text)
    print('Key match:', key_match.group(1) if key_match else None)
    
    if key_match:
        key_val = key_match.group(1)
        post_data = {
            'action': 'cloud',
            'key': key_val,
            'action_token': ''
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'x-token': 'driveseed.org',
            'Referer': url_zfile,
            'X-Requested-With': 'XMLHttpRequest'
        }
        r3 = await client.post(url_zfile, data=post_data, headers=headers)
        print('r3 status:', r3.status_code)
        print('r3 text:', r3.text)

asyncio.run(test())
