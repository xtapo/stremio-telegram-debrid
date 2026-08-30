import httpx
from bs4 import BeautifulSoup

def inspect_pixel():
    url = "https://pixel.hubcloud.cx/?id=1864755802c7d1d04e59e6dc50dd3b3d5ae64077cf05f161d27ce082843d8a75ab92760b2299e65d3a61b4cf814c7571f68b9c50f0aa69e6bec8d2a7f5ed33c5e49671344a6f9afc79c2a51e53d299964a4c036039d7c0d779f787c3094f2006::280060123eb71affc960fb203d26394d"
    r = httpx.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36', 'Referer': 'https://gamerxyt.com/'}, follow_redirects=True, timeout=15.0)
    
    with open("scratch/pixel_page.html", "w", encoding="utf-8") as f:
        f.write(r.text)
        
    soup = BeautifulSoup(r.text, "html.parser")
    print("Links on pixel page:")
    for a in soup.find_all("a", href=True):
        print(f"  [{a.get_text(strip=True)}] -> {a['href']}")
        
    print("\nScripts on pixel page:")
    for s in soup.find_all("script"):
        t = s.string or ""
        for line in t.split("\n"):
            if any(k in line for k in ["http", "var", "const", "window.location", "api", "download", "href"]):
                print("  ", line.strip())

if __name__ == "__main__":
    inspect_pixel()
