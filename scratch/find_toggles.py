import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('dashboard_router.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'enable_source_' in line or 'enable_board_' in line:
        print(f"Line {i+1}: {line.strip()[:100]}")
