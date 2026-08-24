with open("dashboard_router.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "iptv" in line.lower() or "film4k" in line.lower():
        # encode safely
        safe = line.rstrip().encode("ascii", errors="replace").decode("ascii")
        print(f"{i+1}: {safe[:120]}")
