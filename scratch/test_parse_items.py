from bs4 import BeautifulSoup
import re

with open('scratch/4khd_outerbanks.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

items = soup.select('.download-item')
print(f"Total download items in Outer Banks: {len(items)}")

for idx, item in enumerate(items):
    ep_num_el = item.select_one('.episode-number')
    ep_num = ep_num_el.get_text(strip=True) if ep_num_el else None
    
    header_title_el = item.select_one('.download-header .font-semibold')
    header_title = header_title_el.get_text(" ", strip=True) if header_title_el else ""
    
    file_title_el = item.select_one('.file-title')
    file_title = file_title_el.get_text(strip=True) if file_title_el else ""
    
    badges = [b.get_text(strip=True) for b in item.select('.badge')]
    
    links = [(a.get_text(strip=True), a['href']) for a in item.select('a[href]')]
    
    print(f"\nItem #{idx+1}:")
    print(f"  Ep/Season tag: {ep_num}")
    print(f"  Header Title: {header_title}")
    print(f"  File Title: {file_title}")
    print(f"  Badges: {badges}")
    print(f"  Links: {links}")
    if idx > 12:
        print("  ... remaining items omitted ...")
        break
