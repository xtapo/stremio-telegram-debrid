import urllib.request
import urllib.parse
import html
import json

def test_q(q):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://hubcloud.cx/',
        'Accept': 'application/json'
    }
    token = "BLBuI_3M0zIndc8lnxU_oSJJuYQoZ-HIKXkqICte48g_w2A4ajZl"
    url = f"https://hubcloud.cx/drive/search-recover.php?api=search&q={urllib.parse.quote(q)}&page=1&from_ac={token}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print(f"Query [{q}] => Found: {data.get('found')}")
            for h in data.get('hits', []):
                print(f"   -> {h.get('file_name')} ({h.get('size')}) => {h.get('url')}")
    except Exception as e:
        print(f"Query [{q}] Error: {e}")

if __name__ == '__main__':
    test_q(html.unescape("Download Deadpool \u0026#038; Wolverine 2024 1080p"))
    test_q("Deadpool Wolverine 2024 1080p")
    test_q("Deadpool")
    test_q("Loki")
    test_q("Loki S01")
    test_q("Reacher")
