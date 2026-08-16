import urllib.request
from bs4 import BeautifulSoup

def main():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://hubcloud.cx/'
    }
    url = "https://gamerxyt.com/hubcloud.php?host=hubcloud&id=9fm1fbqq04e9qq_&token=TkRaWUd0UnNLOGxHdHFlSTkvamNQaUZubVRsM0RFYmNZZ0hpdWJRZXhTbz0="
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        with open("scratch/gamerxyt_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        soup = BeautifulSoup(html, 'html.parser')
        print("Page URL:", resp.geturl())
        print("Page title:", soup.title.string if soup.title else "None")
        for a in soup.find_all('a', href=True):
            print("Link:", a.get_text(strip=True), "=>", a.get('href'))

if __name__ == '__main__':
    main()
