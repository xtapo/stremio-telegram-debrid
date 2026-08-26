import requests
import json
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def test_source(name, fn):
    try:
        print(f"=== {name} ===")
        fn()
    except Exception as e:
        print(f"  Error: {e}")

def test_ridomovies():
    r = requests.get('https://ridomovies.su/api/search?q=oppenheimer', headers=headers, timeout=10)
    data = r.json()
    items = data.get('data', [])
    print(f"  RidoMovies search items: {len(items)}")
    if items:
        it = items[0]
        print(f"  Item: {it.get('title')} ({it.get('slug')})")
        r_page = requests.get(f"https://ridomovies.su/movies/{it.get('slug')}", headers=headers, timeout=10)
        print(f"  Page len: {len(r_page.text)}")
        # Check iframe
        iframe = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', r_page.text)
        print(f"  Iframes: {iframe}")

def test_clbphimxua():
    r = requests.get('https://clbphimxua.com/wp-json/wp/v2/posts?per_page=5&_embed', headers=headers, timeout=10)
    posts = r.json()
    print(f"  CLBPhimXua posts: {len(posts)}")
    if posts and isinstance(posts, list):
        p = posts[0]
        print(f"  Title: {p.get('title', {}).get('rendered')} - Link: {p.get('link')}")
        content = p.get('content', {}).get('rendered', '')
        iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', content)
        print(f"  Iframes/Embeds: {iframes}")

def test_hoathinh3d():
    r = requests.get('https://hoathinh3d.ad/wp-json/wp/v2/posts?per_page=5', headers=headers, timeout=10)
    print("  HoatHinh3D WP status:", r.status_code)
    # Check web
    r2 = requests.get('https://hoathinh3d.ad/', headers=headers, timeout=10)
    print("  HoatHinh3D Home status:", r2.status_code, "len:", len(r2.text))

def test_yumeianime():
    r = requests.get('https://yumei-anime.com/api/posts?limit=5', headers=headers, timeout=10)
    print("  YumeiAnime API status:", r.status_code)
    r2 = requests.get('https://yumei-anime.com/', headers=headers, timeout=10)
    print("  YumeiAnime Home status:", r2.status_code, "len:", len(r2.text))

def test_phimhdcs():
    r = requests.get('https://phimhdcss.com/', headers=headers, timeout=10)
    print("  PhimHDCS Home status:", r.status_code, "len:", len(r.text))

def test_animevietsub():
    # Bitly link check
    r = requests.get('https://bit.ly/animevietsubtv', headers=headers, allow_redirects=True, timeout=10)
    print("  AnimeVietsub redirect URL:", r.url, "Status:", r.status_code)

def test_yanhh3d():
    r = requests.get('https://bit.ly/yanhh3d', headers=headers, allow_redirects=True, timeout=10)
    print("  Yanhh3d redirect URL:", r.url, "Status:", r.status_code)

test_source("RidoMovies", test_ridomovies)
test_source("CLBPhimXua", test_clbphimxua)
test_source("HoatHinh3D", test_hoathinh3d)
test_source("YumeiAnime", test_yumeianime)
test_source("PhimHDCS", test_phimhdcs)
test_source("AnimeVietsub", test_animevietsub)
test_source("Yanhh3d", test_yanhh3d)
