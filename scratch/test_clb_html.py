import requests
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

r = requests.get('https://clbphimxua.com/', headers=headers)
print("CLB Home status:", r.status_code, "len:", len(r.text))

# Search articles
articles = re.findall(r'<article[\s\S]*?</article>', r.text)
print("Articles found:", len(articles))
for a in articles[:5]:
    t_m = re.search(r'<h[23][^>]*><a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', a)
    img_m = re.search(r'<img[^>]+(?:data-src|src)=["\']([^"\']+)["\']', a)
    if t_m:
        print(f"Title: {t_m.group(2)} -> URL: {t_m.group(1)} | Img: {img_m.group(1) if img_m else ''}")

# Test search
r_search = requests.get('https://clbphimxua.com/?s=kiem', headers=headers)
print("\nSearch 'kiem' status:", r_search.status_code)
search_articles = re.findall(r'<article[\s\S]*?</article>', r_search.text)
print("Search articles found:", len(search_articles))
for a in search_articles[:3]:
    t_m = re.search(r'<h[23][^>]*><a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', a)
    if t_m:
        print(f"  Search result: {t_m.group(2)} -> {t_m.group(1)}")
