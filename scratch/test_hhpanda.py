import sys
import httpx
import re

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://hhpanda.st/"
}

url = "https://streamfree.vip/embed/v/IGv1ZUfv"
r = httpx.get(url, headers=headers)
html = r.text

patch_script = """<base href="https://streamfree.vip/">
<script>
(function() {
    // 1. Disable console devtools detection
    var noop = function() {};
    try {
        window.console.log = noop;
        window.console.clear = noop;
        window.console.table = noop;
        window.console.warn = noop;
        window.console.error = noop;
        window.console.debug = noop;
        window.console.info = noop;
    } catch(e) {}

    // 2. Override document.referrer for bytecode decryption
    try {
        Object.defineProperty(document, 'referrer', {
            get: function() { return 'https://hhpanda.st/'; }
        });
    } catch(e) {}

    // 3. Override outer dimensions to prevent devtools panel detection
    try {
        Object.defineProperty(window, 'outerWidth', {
            get: function() { return window.innerWidth; }
        });
        Object.defineProperty(window, 'outerHeight', {
            get: function() { return window.innerHeight; }
        });
    } catch(e) {}
})();
</script>
"""

if "<head>" in html:
    html = html.replace("<head>", f"<head>{patch_script}", 1)

print("Patched HTML length:", len(html))
print("Contains devtools patch:", "window.console.clear = noop" in html)
