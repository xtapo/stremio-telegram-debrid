import httpx

def test():
    client = httpx.Client(
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Referer': 'https://www.vidking.net/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        },
        follow_redirects=True,
        timeout=10.0
    )
    try:
        r = client.get('https://www.vidking.net/embed/movie/550')
        print("Status:", r.status_code)
        print("Content-Type:", r.headers.get('content-type'))
        print("Body length:", len(r.text))
        print("First 1000 chars:\n", r.text[:1000])
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    test()
