with open("dashboard_router.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if any(k in line.lower() for k in ["vidking", "hdtoday"]):
        print(f"Line {i+1}: {line.strip()[:100]}".encode('ascii', 'replace').decode('ascii'))
