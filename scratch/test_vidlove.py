import httpx
import re

client = httpx.Client(headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=15.0)
r = client.get('https://player.vidlove.cc/assets/index-DCeIiXZS.js')

for m in re.finditer(r'(?:fetch|axios|get|post)\s*\([^\)]+\)', r.text):
    print('Match:', m.group(0)[:150])

for m in re.finditer(r'api\.shows\.st[^\'\"\`\)\s]+', r.text):
    print('Shows API:', m.group(0))
