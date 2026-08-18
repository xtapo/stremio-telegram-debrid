import httpx
import re

r = httpx.get('https://www.vidking.net/assets/VideoPlayer-D5eTfQPp.js', headers={'User-Agent': 'Mozilla/5.0'})
text = r.text

# Let's search for function `al=` or `async function al` or `const al=` or whatever definition of al is
pos = 0
while True:
    idx = text.find('al=', pos)
    if idx == -1:
        break
    print("Found al= at", idx)
    print(text[max(0, idx-50):min(len(text), idx+600)])
    print("="*40)
    pos = idx + 3
