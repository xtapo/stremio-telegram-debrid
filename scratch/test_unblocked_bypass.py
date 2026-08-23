import httpx
from bs4 import BeautifulSoup
import re

client = httpx.Client(headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36', 'Referer': 'https://uhdmovies.autos/'}, follow_redirects=True, timeout=25)
url = 'https://cloud.unblockedgames.world/?sid=a3Y4azk3STZ5RVphb1c0d0pkeDllaWVjc3NTd1dyeHJZSlNRUkszSnJFSGphampKSXNSZWwrcG5LYTJEYkE2UkZIZjJJc3VDQ1hhdW9jVTJmTTFzU29PMlFKZ0MzTmhvSC9NWEh6a0Z2T2VreEtlM3BYTGhmZ2VJNFhrcnRKWWZjaGh6OVMwd0FnMWxEb0RPZ3dqb1hVRTZnRzE4T3FEeWkzcEMyVXpReGx2MGZwWU4vT3hWYVA2NWVNdS81Y1UvVWszbVJrS2hlUUppbG5Sd1dwcXJYeEg5aWh1QlBPcFhCMWJ2Q0Y5UVlwUmlVc3FGUGRDcCtQOEJEeVRncEtiWA=='

print("Step 1: Fetch landing...")
r1 = client.get(url)
soup1 = BeautifulSoup(r1.text, 'html.parser')
form1 = soup1.select_one('form')
data1 = {inp.get('name'): inp.get('value', '') for inp in form1.select('input') if inp.get('name')}

print("Step 2: Post landing form...")
r2 = client.post(form1.get('action') or url, data=data1, headers={'Referer': url})
soup2 = BeautifulSoup(r2.text, 'html.parser')
form2 = soup2.select_one('form')
data2 = {inp.get('name'): inp.get('value', '') for inp in form2.select('input') if inp.get('name')}

print("Step 3: Post form 2...")
r3 = client.post(form2.get('action'), data=data2, headers={'Referer': str(r2.url)})

match_cookie = re.search(r"s_\d+\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", r3.text)
match_go = re.search(r"https?://cloud\.unblockedgames\.world/\?go=([^'\"\s]+)", r3.text)

print('Match Cookie:', match_cookie.groups() if match_cookie else 'None')
print('Match Go:', match_go.groups() if match_go else 'None')

if match_cookie and match_go:
    c_name, c_val = match_cookie.groups()
    go_url = f"https://cloud.unblockedgames.world/?go={match_go.group(1)}"
    client.cookies.set(c_name, c_val, domain='cloud.unblockedgames.world')
    print(f"Step 4: GET {go_url} with cookie {c_name}...")
    r4 = client.get(go_url, headers={'Referer': str(r3.url)})
    print('R4 Status:', r4.status_code)
    print('R4 URL:', r4.url)
    print('R4 text length:', len(r4.text))
    print('R4 snippet:\n', r4.text[:3000])
