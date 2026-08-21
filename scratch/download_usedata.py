import requests

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

js_url = 'https://film4k.net/assets/useData-DtwRclbF.js'
r = requests.get(js_url, headers=headers)
print("useData JS status:", r.status_code)
print("useData JS size:", len(r.text))

with open('scratch/film4k_useData.js', 'w', encoding='utf-8') as f:
    f.write(r.text)
