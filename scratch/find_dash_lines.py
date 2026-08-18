with open('dashboard_router.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'api_system_addons' in line or 'HDToday' in line or 'hdtoday' in line:
        print(f"Line {i+1}: {line.strip()[:100]}")
