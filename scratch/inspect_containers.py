from bs4 import BeautifulSoup

with open('scratch/4khd_avatar.html', 'r', encoding='utf-8') as f:
    soup_m = BeautifulSoup(f.read(), 'html.parser')

print("=== AVATAR DOM STRUCTURE ===")
# Find all elements that contain download links
for dl in soup_m.find_all('a', href=lambda h: h and ('hubcloud' in h or 'hubdrive' in h)):
    # Walk up to find the enclosing box/container
    container = dl.find_parent(class_=lambda c: c and any(k in c for k in ['grid', 'card', 'box', 'download', 'format', 'item', 'quality', 'content', 'season', 'episode', 'link']))
    heading = container.find_previous(['h2', 'h3', 'h4', 'h5', 'p', 'div'], class_=lambda c: c and any(k in str(c) for k in ['title', 'quality', 'header', 'name'])) if container else None
    print(f"\nLink: {dl.get_text(strip=True)} -> {dl['href']}")
    if container:
        print(f"Container tag: <{container.name} class='{container.get('class')}'>")
        print("Container text:", " ".join(container.get_text(" ", strip=True).split())[:150])

with open('scratch/4khd_outerbanks.html', 'r', encoding='utf-8') as f:
    soup_s = BeautifulSoup(f.read(), 'html.parser')

print("\n=== OUTER BANKS SERIES DOM STRUCTURE ===")
# Let's inspect the first 10 download link containers
for dl in soup_s.find_all('a', href=lambda h: h and ('hubcloud' in h or 'hubdrive' in h))[:8]:
    container = dl.find_parent(class_=lambda c: c and any(k in c for k in ['grid', 'card', 'box', 'download', 'format', 'item', 'quality', 'content', 'season', 'episode', 'link']))
    prev_headings = [h.get_text(strip=True) for h in dl.find_all_previous(['h2', 'h3', 'h4', 'h5', 'strong', 'b'], limit=3)]
    print(f"\nLink: {dl.get_text(strip=True)} -> {dl['href']}")
    print(f"Nearest headings before: {prev_headings}")
    if container:
        print(f"Container tag: <{container.name} class='{container.get('class')}'>")
        print("Container text:", " ".join(container.get_text(" ", strip=True).split())[:150])
