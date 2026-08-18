import httpx
import re

r = httpx.get('https://www.vidking.net/assets/VideoPlayer-D5eTfQPp.js', headers={'User-Agent': 'Mozilla/5.0'})
text = r.text

idx = text.find('mvm1')
if idx != -1:
    print("Found mvm1 at", idx)
    print(text[max(0, idx-500):min(len(text), idx+1000)])
else:
    print("mvm1 not found")

idx2 = text.find('/seed')
if idx2 != -1:
    print("\nFound /seed at", idx2)
    print(text[max(0, idx2-300):min(len(text), idx2+500)])
