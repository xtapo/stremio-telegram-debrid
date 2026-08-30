import re
from bs4 import BeautifulSoup

def analyze_gamerxyt():
    with open("scratch/reacher_gamerxyt.html", "r", encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")
    with open("scratch/gamerxyt_links.txt", "w", encoding="utf-8") as out:
        out.write(f"Page title: {soup.title.string if soup.title else 'No title'}\n\n")
        out.write("--- Links found in GamerXYT page ---\n")
        for a in soup.find_all("a", href=True):
            t = a.get_text(" ", strip=True)
            href = a['href']
            out.write(f"[{t}] -> {href}\n")

        out.write("\n--- Script tags / variables ---\n")
        for script in soup.find_all("script"):
            text = script.string or ""
            for line in text.split("\n"):
                if any(k in line for k in ["http", "var", "const", "let", "window.location", "pixeldrain", "workers"]):
                    out.write(f"JS line: {line.strip()}\n")

if __name__ == "__main__":
    analyze_gamerxyt()
