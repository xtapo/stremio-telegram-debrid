import os
import glob
import re

for txt_path in glob.glob("scratch/*_strings.txt"):
    name = os.path.basename(txt_path).replace("_strings.txt", "")
    with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = [line.strip() for line in f if line.strip()]
    
    urls = [l for l in lines if l.startswith("http://") or l.startswith("https://")]
    api_routes = [l for l in lines if l.startswith("/") and len(l) > 3 and not l.startswith("/data") and not l.startswith("/org") and not l.startswith("/com")]
    
    print(f"=== {name} ===")
    print("  URLs:", list(set(urls))[:6])
    print("  Routes:", list(set(api_routes))[:6])
