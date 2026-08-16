import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

with open("scratch/movie_page.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')
content = soup.find('div', class_='entry-content') or soup.find('article')

if content:
    for a in content.find_all('a', href=True):
        href = a.get('href')
        text = a.get_text(strip=True)
        print(f"DL Button Text: {text!r} | Link: {href}")
