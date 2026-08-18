import httpx

r = httpx.get('https://www.vidking.net/assets/VideoPlayer-D5eTfQPp.js', headers={'User-Agent': 'Mozilla/5.0'})
text = r.text

idx = text.find('/seed')
start = max(0, idx - 2500)
end = min(len(text), idx + 2500)

with open('scratch/decryption_section.js', 'w', encoding='utf-8') as f:
    f.write(text[start:end])

print(f"Wrote decryption section from {start} to {end} ({end-start} chars)")
