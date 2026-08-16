import urllib.request
import json

def main():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://hubcloud.cx/drive/search-recover.php?from_ac=hmYhsHGW_XieHS-QxxrLfjLheOKPxAg677mvx-7ih6YKdR7_VjOM&q=RG93bmxvYWQgTG9raSAxMDgwcA',
        'Accept': 'application/json'
    }
    url = "https://hubcloud.cx/drive/search-recover.php?api=search&q=Download+Loki+1080p&page=1&from_ac=hmYhsHGW_XieHS-QxxrLfjLheOKPxAg677mvx-7ih6YKdR7_VjOM"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print("Response:", json.dumps(data, indent=2))

if __name__ == '__main__':
    main()
