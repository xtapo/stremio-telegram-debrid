import httpx

def test_stream_links():
    url_pixel = "https://pixel.hubcloud.cx/?id=1864755802c7d1d04e59e6dc50dd3b3d5ae64077cf05f161d27ce082843d8a75ab92760b2299e65d3a61b4cf814c7571f68b9c50f0aa69e6bec8d2a7f5ed33c5e49671344a6f9afc79c2a51e53d299964a4c036039d7c0d779f787c3094f2006::280060123eb71affc960fb203d26394d"
    url_worker = "https://floral-forest-499c.ceromig960.workers.dev/034476ddc075de42b109b66fe18134ffc3ac6425ad6ba65b9123840046955eb3bbbbb559be5cdf8719829c13c6570f3c::32c2aa77c6abfb9911c360297f6aa4a9/1397996994/Reacher.S01E01.1080p.WEB-DL.Hindi.5.1-English.5.1.ESub.x264-[moviesdrives.com].mkv"

    headers_worker = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://gamerxyt.com/",
    }

    print("--- Testing pixel.hubcloud.cx ---")
    try:
        r1 = httpx.get(url_pixel, headers=headers_worker, follow_redirects=False, timeout=10.0)
        print("Pixel status:", r1.status_code)
        print("Pixel headers:", r1.headers)
        if r1.status_code in (301, 302, 307, 308):
            print("Pixel redirect location:", r1.headers.get("location"))
        else:
            print("Pixel text:", r1.text[:300])
    except Exception as e:
        print("Pixel error:", e)

    print("\n--- Testing workers.dev with various referers ---")
    for ref in ["https://gamerxyt.com/", "https://hubcloud.cx/", "https://hubcloud.ist/", "https://gamerxyt.com/hubcloud.php", None]:
        h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        if ref:
            h["Referer"] = ref
        try:
            r2 = httpx.head(url_worker, headers=h, follow_redirects=True, timeout=10.0)
            print(f"Worker (Referer: {ref}) status: {r2.status_code}, content-type: {r2.headers.get('content-type')}, length: {r2.headers.get('content-length')}")
        except Exception as e:
            print(f"Worker (Referer: {ref}) error: {e}")

if __name__ == "__main__":
    test_stream_links()
