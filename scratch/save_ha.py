import httpx

r = httpx.get('https://www.vidking.net/assets/VideoPlayer-D5eTfQPp.js', headers={'User-Agent': 'Mozilla/5.0'})
text = r.text

idx = text.find('async function ha(')
start = idx
end = min(len(text), idx + 2500)

with open('scratch/ha_function.js', 'w', encoding='utf-8') as f:
    f.write(text[start:end])

print(f"Wrote ha function from {start} to {end}")
