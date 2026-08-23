import urllib.request
import re
import json

def parse_m3u(content, country_code=""):
    channels = []
    lines = content.splitlines()
    curr = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            curr = {}
            tvg_id_m = re.search(r'tvg-id="([^"]*)"', line)
            tvg_name_m = re.search(r'tvg-name="([^"]*)"', line)
            tvg_logo_m = re.search(r'tvg-logo="([^"]*)"', line)
            group_m = re.search(r'group-title="([^"]*)"', line)
            
            parts = line.split(",", 1)
            title = parts[1].strip() if len(parts) > 1 else "Channel"
            
            curr["title"] = title
            curr["tvg_id"] = tvg_id_m.group(1) if tvg_id_m else ""
            curr["tvg_name"] = tvg_name_m.group(1) if tvg_name_m else ""
            curr["tvg_logo"] = tvg_logo_m.group(1) if tvg_logo_m else ""
            curr["group"] = group_m.group(1) if group_m else "General"
            curr["country"] = country_code.upper()
        elif curr is not None and not line.startswith("#"):
            curr["url"] = line
            # generate safe unique ID
            ch_slug = re.sub(r'[^a-zA-Z0-9]', '_', curr["tvg_id"] or curr["title"]).strip('_').lower()
            curr["id"] = f"iptv:{country_code.lower()}:{ch_slug}"
            channels.append(curr)
            curr = None
    return channels

for code in ['vn', 'us', 'jp', 'fr', 'kr', 'uk', 'de', 'ca', 'au', 'sg', 'th', 'in', 'cn', 'es', 'it', 'br', 'ru']:
    url = f"https://iptv-org.github.io/iptv/countries/{code}.m3u"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            chs = parse_m3u(content, code)
            print(f"{code.upper()}: {len(chs)} channels. Sample: {chs[0]['title'] if chs else 'None'} -> {chs[0]['url'] if chs else ''}")
    except Exception as e:
        print(f"{code.upper()} Error: {e}")
