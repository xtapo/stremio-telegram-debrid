import httpx
from bs4 import BeautifulSoup
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://hdtoday.sc/'
}
client = httpx.Client(headers=headers, timeout=15.0, follow_redirects=True)

for url in [
    'https://hdtoday.sc/movie/avatar-7yeqHJL09WY',
    'https://hdtoday.sc/tv/the-legend-of-korra-EOX7CgngyYz'
]:
    r = client.get(url)
    soup = BeautifulSoup(r.text, 'html.parser')
    
    title = soup.select_one('.heading-name a, h2.heading-name')
    desc = soup.select_one('.description')
    poster = soup.select_one('.film-poster img')
    watch_div = soup.select_one('.detail_page-watch')
    
    # Details in sidebar
    row_line = soup.select('.elements .row-line')
    details = {}
    for row in row_line:
        type_span = row.select_one('.type')
        if type_span:
            label = type_span.text.strip().replace(':', '')
            val = row.text.replace(type_span.text, '').strip()
            details[label] = val
            
    print('=== URL:', url)
    print('Title:', title.text.strip() if title else 'N/A')
    print('Poster:', poster.get('src') if poster else 'N/A')
    print('Watch Div:', watch_div.attrs if watch_div else 'N/A')
    print('Description:', desc.text.strip()[:150] if desc else 'N/A')
    print('Details:', details)
