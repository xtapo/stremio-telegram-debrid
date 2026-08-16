import urllib.request
from bs4 import BeautifulSoup

def main():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://new2.moviesdrive.christmas/'
    }
    url = "https://hubcloud.cx/drive/search-recover.php?from_ac=hmYhsHGW_XieHS-QxxrLfjLheOKPxAg677mvx-7ih6YKdR7_VjOM&q=RG93bmxvYWQgTG9raSAxMDgwcA"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        for line in html.splitlines():
            if any(k in line for k in ['FROM_AC_TOKEN', 'Q_INITIAL', 'fetchPage', 'hits', 'token']):
                print(line)

if __name__ == '__main__':
    main()
