import httpx
import re

client = httpx.Client(headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=15.0)

# Vidup chunk 294
r = client.get('https://vidup.to/_next/static/chunks/294-2defee769d156d54.js')
print('VidUp chunk len:', len(r.text))
for m in re.finditer(r'https?://[a-zA-Z0-9_\-\./]+', r.text):
    print(m.group(0))
