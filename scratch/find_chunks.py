with open("scratch/embedUrl.js", "r", encoding="utf-8") as f:
    code = f.read()

import re
matches = re.findall(r'stream\.ernax\.pro[^\s"\'`]*', code)
print("stream.ernax.pro matches in embedUrl.js:", matches)

# Let's check other chunks in index-CzOW_YHx.js
with open("scratch/index.js", "w", encoding="utf-8") as f:
    import urllib.request
    req = urllib.request.Request("https://ernax.pro/assets/index-CzOW_YHx.js", headers={'User-Agent': 'Mozilla/5.0'})
    f.write(urllib.request.urlopen(req).read().decode('utf-8', errors='ignore'))

with open("scratch/index.js", "r", encoding="utf-8") as f:
    idx_code = f.read()

chunks = re.findall(r'assets/[a-zA-Z0-9_\-]+\.js', idx_code)
print("Found chunks in index.js:", set(chunks))
