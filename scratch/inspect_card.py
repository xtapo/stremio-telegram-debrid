from bs4 import BeautifulSoup

with open('scratch/4khdhub_search.html', 'r', encoding='utf-8') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')
# find first a tag that wraps or is inside movie-card
for a in soup.find_all('a'):
    if a.find(class_=lambda c: c and 'movie-card' in c) or ('movie-card' in str(a.get('class', ''))):
        print("Found card <a>:")
        print(a.prettify()[:1000])
        break
    if '/rush-' in a.get('href', '') or '-movie-' in a.get('href', '') or '-series-' in a.get('href', ''):
        print("Found post <a>:")
        print(a.prettify()[:1000])
        break
