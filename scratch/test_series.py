import urllib.request
import json
from bs4 import BeautifulSoup

def main():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://new2.moviesdrive.christmas/'
    }
    # Search for Loki or Reacher
    req = urllib.request.Request('https://new2.moviesdrive.christmas/search.php?q=loki&page=1', headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print("Search hits for 'loki':")
        for hit in data.get('hits', []):
            doc = hit.get('document', {})
            print(f"Title: {doc.get('post_title')} | Permalink: {doc.get('permalink')}")
            
        first_post = data.get('hits', [{}])[0].get('document', {}).get('permalink')
        if first_post:
            full_url = "https://new2.moviesdrive.christmas" + first_post
            print("\nFetching series page:", full_url)
            req2 = urllib.request.Request(full_url, headers=headers)
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                html = resp2.read().decode('utf-8', errors='ignore')
                with open("scratch/series_page.html", "w", encoding="utf-8") as f:
                    f.write(html)
                soup = BeautifulSoup(html, 'html.parser')
                content = soup.find('div', class_='entry-content') or soup.find('article')
                if content:
                    for a in content.find_all('a', href=True):
                        href = a.get('href')
                        text = a.get_text(strip=True)
                        if 'hubcloud' in href.lower() or 'drive' in href.lower() or 'link' in href.lower():
                            print(f"Series Link: [{text}] => {href}")

if __name__ == '__main__':
    main()
