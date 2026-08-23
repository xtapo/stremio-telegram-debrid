import asyncio
import httpx
from bs4 import BeautifulSoup
import re
import urllib.parse

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
real_link = 'https://cloud.unblockedgames.world/?sid=a3Y4azk3STZ5RVphb1c0d0pkeDllaWVjc3NTd1dyeHJZSlNRUkszSnJFSGphampKSXNSZWwrcG5LYTJEYkE2UkZIZjJJc3VDQ1hhdW9jVTJmTTFzU29PMlFKZ0MzTmhvSC9NWEh6a0Z2T2RqWmdlSk9pYmVnRVpFYzFiVlNIcFB4NDY5NFJQUjZBR0Mvd1Q5QXp0UmJ5dmNpME9HajlVWlRReWRybnJNYWJwdHhxZ1NyVVM2TEZjQ3F1VThzSkR5NExYT3huY1A1MUltOTBJY29wcnA1MUVQSVJ3SVp1NWFiSERpTDNsL2lDb3ZOY2p0OFd2MUlNcHhHaGpQNGJmSg=='

async def test():
    client = httpx.AsyncClient(headers={'User-Agent': USER_AGENT, 'Referer': 'https://uhdmovies.autos/'}, follow_redirects=True, timeout=25)
    r1 = await client.get(real_link)
    soup1 = BeautifulSoup(r1.text, 'html.parser')
    form1 = soup1.select_one('form')
    data1 = {inp.get('name'): inp.get('value', '') for inp in form1.select('input') if inp.get('name')}
    r2 = await client.post(form1.get('action') or real_link, data=data1, headers={'Referer': real_link})
    soup2 = BeautifulSoup(r2.text, 'html.parser')
    form2 = soup2.select_one('form')
    data2 = {inp.get('name'): inp.get('value', '') for inp in form2.select('input') if inp.get('name')}
    r3 = await client.post(form2.get('action'), data=data2, headers={'Referer': str(r2.url)})
    match_cookie = re.search(r"s_\d+\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", r3.text)
    match_go = re.search(r"https?://[^'\"\s]+/\?go=([^'\"\s]+)", r3.text)
    c_name, c_val = match_cookie.groups()
    go_param = match_go.group(1)
    base_domain = urllib.parse.urlsplit(str(r3.url)).netloc
    go_url = f'https://{base_domain}/?go={go_param}'
    client.cookies.set(c_name, c_val, domain=base_domain)
    r4 = await client.get(go_url, headers={'Referer': str(r3.url)})
    meta_refresh = re.search(r'content=[\"\']\d+;\s*url=([^\"\']+)[\"\']', r4.text, re.I)
    target_url = meta_refresh.group(1)
    print('Target url from r4:', target_url)
    r5 = await client.get(target_url, headers={'Referer': str(r4.url)})
    file_match = re.search(r'window\.location\.replace\([\"\']([^\"\']+)[\"\']\)', r5.text)
    driveseed_file_url = urllib.parse.urljoin(str(r5.url), file_match.group(1)) if file_match else str(r5.url)
    print('Driveseed file url:', driveseed_file_url)
    r6 = await client.get(driveseed_file_url, headers={'Referer': str(r5.url)})
    soup6 = BeautifulSoup(r6.text, 'html.parser')
    for a in soup6.select('a[href]'):
        text = a.text.strip().encode('ascii', 'ignore').decode()
        print('Driveseed link:', text, '->', a['href'])

asyncio.run(test())
