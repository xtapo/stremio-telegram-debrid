import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('dashboard_router.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if any(k in line.lower() for k in ['gemini_api_key', 'custom_ai_api_key', 'torbox_api_key', 'real_debrid']):
        print(f"Line {i+1}: {line.strip()[:100]}")
