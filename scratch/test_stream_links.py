import urllib.request
import urllib.parse

def test_link(url, name):
    # parse and quote path properly
    p = urllib.parse.urlsplit(url)
    clean_path = urllib.parse.quote(p.path)
    clean_url = urllib.parse.urlunsplit((p.scheme, p.netloc, clean_path, p.query, p.fragment))
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://gamerxyt.com/'
    }
    req = urllib.request.Request(clean_url, headers=headers, method='GET')
    req.headers['Range'] = 'bytes=0-1024'
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[{name}] Status: {resp.status}, Content-Type: {resp.headers.get('Content-Type')}, Content-Length: {resp.headers.get('Content-Length')}, Content-Range: {resp.headers.get('Content-Range')}, URL: {resp.geturl()[:80]}...")
    except Exception as e:
        print(f"[{name}] Error: {e}")

if __name__ == '__main__':
    url1 = "https://pixel.hubcloud.cx/?id=b46c74b9d75e3b7803498fd952fe632e0afe8766c94144a3a8679e3a8893c2bb613980286ca7caa2f3fa29e08e56edd322470150619644c34e68a357246831d0c615900873fc11c0c2ff54846685946be01dbe62e41ef3cfc14e3a9dd80714d5::d5f378b4a49281cb0767b96dbcfc5fc8"
    url2 = "https://green-limit-7572.terapiyo236.workers.dev/05995cf646a94e26a2308309d62181ff35ceee0520bae94f7fd73e5c7ff1c2daa35f7accecb14fa4ba11851e9f100ddd::ced9e26706983558939b091d6b6178aa/1397996304/Download Three Thousand Years of Longing (2022) WEB-DL English With Subtitles Full Movie 720p -moviesdrives.com.mkv"
    test_link(url1, "Pixel Hubcloud")
    test_link(url2, "Workers Dev Direct Stream")
