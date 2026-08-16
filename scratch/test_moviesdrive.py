import urllib.request
from bs4 import BeautifulSoup

def main():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://new2.moviesdrive.christmas/'
    }
    url = "https://new2.moviesdrive.christmas/deadpool-wolverine-2024/"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        with open("scratch/movie_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        soup = BeautifulSoup(html, 'html.parser')
        links = soup.find_all('a', href=True)
        print("Page title:", soup.title.string if soup.title else "None")
        print(f"Total links: {len(links)}")
        for l in links:
            href = l.get('href')
            text = l.get_text(strip=True)
            # print if looks like download link
            if any(k in href.lower() for k in ['hubcloud', 'gdflix', 'drive', 'download', 'fastdl', 'katdrive', 'kolop', 'pixel', 'link', 'hblinks', 'mdrive', 'redirect']):
                print(f"Text: [{text}] => Href: {href}")

if __name__ == '__main__':
    main()
