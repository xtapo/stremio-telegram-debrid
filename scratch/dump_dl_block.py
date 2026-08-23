from bs4 import BeautifulSoup

with open('scratch/4khd_avatar.html', 'r', encoding='utf-8') as f:
    soup_m = BeautifulSoup(f.read(), 'html.parser')

# Find the parent of download links with class or structure
dl = soup_m.find('a', href=lambda h: h and 'hubcloud' in h)
if dl:
    parent = dl
    for _ in range(5):
        if parent.parent:
            parent = parent.parent
    print("=== AVATAR PARENT BLOCK ===")
    print(parent.prettify()[:2500])

with open('scratch/4khd_outerbanks.html', 'r', encoding='utf-8') as f:
    soup_s = BeautifulSoup(f.read(), 'html.parser')

dl_s = soup_s.find('a', href=lambda h: h and 'hubcloud' in h)
if dl_s:
    parent_s = dl_s
    for _ in range(5):
        if parent_s.parent:
            parent_s = parent_s.parent
    print("=== OUTER BANKS PARENT BLOCK ===")
    print(parent_s.prettify()[:2500])
