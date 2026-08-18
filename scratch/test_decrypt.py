import urllib.request
import urllib.parse
import json
import base64

def int32(x):
    x = x & 0xFFFFFFFF
    if x >= 0x80000000:
        return x - 0x100000000
    return x

def uint32(x):
    return x & 0xFFFFFFFF

def imul(a, b):
    return ((int32(a) * int32(b)) & 0xFFFFFFFF)

def Mt(i, l):
    i = uint32(i)
    l = l & 31
    if l == 0:
        return i
    return uint32((i << l) | (i >> (32 - l)))

def ue(i):
    i = uint32(i)
    i = uint32(i ^ (i >> 16))
    i = imul(i, 2246822507)
    i = uint32(i ^ (i >> 13))
    i = imul(i, 3266489909)
    return uint32(i ^ (i >> 16))

def tr(i, l):
    d = [0] * 61
    u = 2166136261
    for char in i:
        u = imul(u ^ ord(char), 16777619)
    u = ue(u)
    m = ue(u ^ ue(uint32(l) ^ 2654435769))
    for v in range(8):
        N = m % 61
        m = Mt(uint32(m + 2654435769), 7 + (7 & v))
        d[N] = uint32(m ^ ue(m))
        m = ue(uint32(m + N))
    return {"S": d, "acc": ue(uint32(2779096485 ^ m))}

def sr(state, l):
    d = state["S"]
    u = state["acc"]
    m = u % 61
    v = -1 if (m in range(len(d))) else 0 # 0 - +(m in d) in JS: +(true)=1 -> 0-1 = -1
    dm = d[m] if m < len(d) else 0
    C = uint32(dm ^ imul(2654435769, l + 1))
    x = uint32((u ^ C) | (u & C & v))
    b = uint32(Mt(uint32(x + u), 31 & m) ^ Mt(u, 31 & imul(m, 7)))
    j = ue(uint32(b + 2654435769))
    d[m] = j
    state["acc"] = j
    return j

def rr(i, l, d):
    u = i.replace('-', '+').replace('_', '/')
    u = u.ljust(4 * ((len(u) + 3) // 4), '=')
    raw = base64.b64decode(u)
    v = bytearray(raw)
    
    state = tr(l, d)
    C = 0
    x = 0
    while x < len(v):
        b = sr(state, C)
        C += 1
        v[x] ^= (b & 255)
        x += 1
        if x < len(v):
            v[x] ^= ((b >> 8) & 255)
            x += 1
        if x < len(v):
            v[x] ^= ((b >> 16) & 255)
            x += 1
        if x < len(v):
            v[x] ^= ((b >> 24) & 255)
            x += 1
    return v[4:].decode('utf-8', errors='ignore')

# Test fetching Fight Club (550)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Referer': 'https://ernax.pro/',
    'Origin': 'https://ernax.pro'
}

tmdb_id = 550
print("Fetching seed...")
req = urllib.request.Request(f"https://api.speedracelight.com/seed?mediaId={tmdb_id}", headers=headers)
seed_data = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))
seed = seed_data['seed']
print("Seed:", seed)

params = urllib.parse.urlencode({
    'title': 'Fight Club',
    'mediaType': 'movie',
    'year': '1999',
    'episodeId': '1',
    'seasonId': '1',
    'tmdbId': str(tmdb_id),
    'imdbId': 'tt0137523',
    'enc': '2',
    'seed': seed
})

print("Fetching encrypted sources...")
req2 = urllib.request.Request(f"https://api.speedracelight.com/cdn/sources-with-title?{params}", headers=headers)
enc_text = urllib.request.urlopen(req2).read().decode('utf-8')
print("Encrypted response length:", len(enc_text))

decrypted = rr(enc_text, seed, tmdb_id)
print("Decrypted JSON:")
print(decrypted)
