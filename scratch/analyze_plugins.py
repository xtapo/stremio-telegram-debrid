import urllib.request
import zipfile
import io
import json
import re

req = urllib.request.Request('https://0cs3.onii.pp.ua/movie/plugins.json', headers={'User-Agent': 'Mozilla/5.0'})
plugins = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))

print(f"Total plugins: {len(plugins)}")

def get_dex_strings(dex_bytes):
    strings = re.findall(rb'[\x20-\x7e]{4,}', dex_bytes)
    return [s.decode('ascii', errors='ignore') for s in strings]

results = {}

for p in plugins:
    name = p['name']
    url = p['url']
    if name == '1Sync':
        continue
    try:
        data = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})).read()
        zf = zipfile.ZipFile(io.BytesIO(data))
        dex = zf.read('classes.dex')
        strings = get_dex_strings(dex)
        http_urls = [s for s in strings if s.startswith('http://') or s.startswith('https://')]
        domains = set()
        for u in http_urls:
            m = re.match(r'https?://([^/]+)', u)
            if m:
                d = m.group(1)
                if not any(x in d for x in ['schema.org', 'w3.org', 'google.com', 'duckduckgo.com', 'github.com', 'lagradost']):
                    domains.add(u)
        
        endpoints = [s for s in strings if any(k in s.lower() for k in ['/api', 'search', 'tim-kiem', 'ajax', 'embed', 'player', 'm3u8', 'v1/', 'v2/', 'graphql', 'stream', 'episode']) and not any(x in s for x in ['com/', 'org/', 'java/'])]
        
        results[name] = {
            "name": name,
            "language": p.get("language", "vi"),
            "tvTypes": p.get("tvTypes", []),
            "domains": list(domains),
            "endpoints": endpoints[:15]
        }
        print(f"=== {name} ({p.get('language', 'vi')}) ===")
        print(f"  Domains: {list(domains)}")
        print(f"  Sample endpoints/patterns: {endpoints[:10]}")
    except Exception as e:
        print(f"=== {name} ERROR: {e} ===")

with open('scratch/plugins_summary.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
