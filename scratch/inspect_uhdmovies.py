import httpx
from bs4 import BeautifulSoup
import re
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

client = httpx.Client(headers=headers, follow_redirects=True, timeout=20)

def search(query):
    url = f"https://uhdmovies.autos/search/{query}"
    resp = client.get(url)
    soup = BeautifulSoup(resp.text, 'html.parser')
    results = []
    
    # Check grid elements or articles
    for a in soup.select('a'):
        href = a.get('href', '')
        if href and 'uhdmovies.autos' in href and ('/download-' in href or href.count('/') >= 4 and not href.endswith('/search/') and not '/category/' in href and not '/tag/' in href and not '/page/' in href):
            title = a.get('title') or a.get_text(strip=True)
            if title and len(title) > 5 and not any(r['url'] == href for r in results):
                results.append({'title': title, 'url': href})
    
    if not results:
        print("No results found with heuristic. Sample links:")
        for a in soup.select('a')[:30]:
            print(" -", a.get('href'), "-->", a.get_text(strip=True)[:50])
            
    return results

def inspect_post(url):
    print(f"\n--- Inspecting Post: {url} ---")
    resp = client.get(url)
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    title = soup.select_one('h1.entry-title, h1')
    print("Title:", title.get_text(strip=True) if title else "No title")
    
    # Let's inspect entry content links and text
    content = soup.select_one('.entry-content, article, div.content')
    if content:
        print("\nAll links in content:")
        for p in content.find_all(['p', 'div', 'h3', 'h4', 'span']):
            # check if it has buttons or download text
            text = p.get_text(strip=True)
            a_tags = p.find_all('a')
            if a_tags and ('1080p' in text or '720p' in text or '2160p' in text or '4k' in text.lower() or 'download' in text.lower() or 'gdrive' in text.lower() or 'hubcloud' in text.lower() or 'drive' in text.lower()):
                print(f"Section text: {text[:100]}...")
                for a in a_tags:
                    print(f"   -> Link: [{a.get_text(strip=True)}] Href: {a.get('href')} Class: {a.get('class')}")

if __name__ == '__main__':
    items = search('avatar')
    print(f"Search results for 'avatar': {len(items)}")
    for i, it in enumerate(items[:5]):
        print(f"[{i}] {it['title']} -> {it['url']}")
    
    if items:
        inspect_post(items[0]['url'])
