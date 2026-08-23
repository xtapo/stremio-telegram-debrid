import httpx
from bs4 import BeautifulSoup
import re

client = httpx.Client(headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36', 'Referer': 'https://uhdmovies.autos/'}, follow_redirects=True, timeout=20)
url = 'https://cloud.unblockedgames.world/?sid=a3Y4azk3STZ5RVphb1c0d0pkeDllaWVjc3NTd1dyeHJZSlNRUkszSnJFSGphampKSXNSZWwrcG5LYTJEYkE2UkZIZjJJc3VDQ1hhdW9jVTJmTTFzU29PMlFKZ0MzTmhvSC9NWEh6a0Z2T2VreEtlM3BYTGhmZ2VJNFhrcnRKWWZjaGh6OVMwd0FnMWxEb0RPZ3dqb1hVRTZnRzE4T3FEeWkzcEMyVXpReGx2MGZwWU4vT3hWYVA2NWVNdS81Y1UvVWszbVJrS2hlUUppbG5Sd1dwcXJYeEg5aWh1QlBPcFhCMWJ2Q0Y5UVlwUmlVc3FGUGRDcCtQOEJEeVRncEtiWA=='
r1 = client.get(url)
soup1 = BeautifulSoup(r1.text, 'html.parser')
form1 = soup1.select_one('form')
data1 = {inp.get('name'): inp.get('value', '') for inp in form1.select('input') if inp.get('name')}

r2 = client.post(form1.get('action') or url, data=data1, headers={'Referer': url})
soup2 = BeautifulSoup(r2.text, 'html.parser')
form2 = soup2.select_one('form')
data2 = {inp.get('name'): inp.get('value', '') for inp in form2.select('input') if inp.get('name')}

r3 = client.post(form2.get('action'), data=data2, headers={'Referer': str(r2.url)})
soup3 = BeautifulSoup(r3.text, 'html.parser')

print('--- Script tags in R3 ---')
for s in soup3.select('script'):
    st = s.get_text()
    if len(st) > 20 and not 'google' in st and not 'vidverto' in st and not 'challenge-platform' in st:
        print('-----------------------------------------')
        print(st)

print('--- All elements with id ---')
for el in soup3.find_all(id=True):
    print(el.name, el.get('id'), el.get('class'), el.get_text(strip=True)[:60])
