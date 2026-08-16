import urllib.request
import json

def main():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://hubcloud.cx/drive/search-recover.php?from_ac=1t-OBKtmgGvpSMlAAfO11hFHSn4zjs6pxm1u9URmZBsBZqta4ESI&q=RG93bmxvYWQgRGVhZHBvb2wgJiMwMzg7IFdvbHZlcmluZSAyMDI0IDQ4MHA',
        'Accept': 'application/json'
    }
    url = "https://hubcloud.cx/drive/search-recover.php?api=search&q=Download+Deadpool+%26%23038%3B+Wolverine+2024+480p&page=1&from_ac=1t-OBKtmgGvpSMlAAfO11hFHSn4zjs6pxm1u9URmZBsBZqta4ESI"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print("API Response:", json.dumps(data, indent=2))

if __name__ == '__main__':
    main()
