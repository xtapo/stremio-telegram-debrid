import urllib.parse
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

def parse_stremio_extra(extra_str: str, query_params: dict):
    genre = None
    search = None
    skip = 0
    
    # 1. Parse from query_params first if present
    if "genre" in query_params: genre = query_params["genre"]
    if "search" in query_params: search = query_params["search"]
    if "skip" in query_params:
        try: skip = int(query_params["skip"])
        except ValueError: pass

    # 2. Parse from extra path string if provided
    if extra_str:
        clean_extra = extra_str
        if clean_extra.endswith(".json"):
            clean_extra = clean_extra[:-5]
            
        parts = re.split(r'[/&]', clean_extra)
        for part in parts:
            if not part:
                continue
            if "=" in part:
                k, v = part.split("=", 1)
                k = urllib.parse.unquote(k).strip()
                v = urllib.parse.unquote(v).strip()
                if k == "genre" and not genre:
                    genre = v
                elif k == "search" and not search:
                    search = v
                elif k == "skip":
                    try:
                        skip = int(v)
                    except ValueError:
                        pass

    return genre, search, skip

# Test cases
test_cases = [
    ("genre=Vi%E1%BB%87t%20Nam&skip=100.json", {}),
    ("genre=Việt Nam/skip=20.json", {}),
    ("skip=30.json", {}),
    ("genre=Hentai%2018%2B.json", {}),
    (".json", {"skip": "50", "genre": "Nhật Bản"}),
]

for extra_str, qp in test_cases:
    g, s, sk = parse_stremio_extra(extra_str, qp)
    print(f"Extra: '{extra_str}' | QP: {qp}")
    print(f"  -> Parsed: genre='{g}', search='{s}', skip={sk}\n")
