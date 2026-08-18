import base64
import json
import time
import httpx

Hl = [
    1116352408, 1899447441, 3049323471, 3921009573,
    961987163, 1508970993, 2453635748, 2870763221,
    3624381080, 310598401, 607225278, 1426881987,
    1925078388, 2162078206, 2614888103, 3248222580
]
_f = [1732584193, 4023233417, 2562383102, 271733878]
Js = 61
Sf = 8
ms = 2654435769
Ys = [109, 118, 109, 49]  # b"mvm1"

def u32(val: int) -> int:
    return val & 0xFFFFFFFF

def imul(a: int, b: int) -> int:
    # 32-bit signed integer multiplication wrapped to uint32
    a = a & 0xFFFFFFFF
    b = b & 0xFFFFFFFF
    if a >= 0x80000000:
        a -= 0x100000000
    if b >= 0x80000000:
        b -= 0x100000000
    return (a * b) & 0xFFFFFFFF

def bf(l: int) -> bool:
    return ((l * (l + 1)) & 1) == 0

def If(l: int) -> bool:
    return ((l * (l + 1)) & 1) == 1

def ci(l: int) -> int:
    l = u32(l)
    l ^= (l >> 16)
    l = u32(imul(l, 2246822507))
    l ^= (l >> 13)
    l = u32(imul(l, 3266489909))
    l ^= (l >> 16)
    return u32(l)

def ps(l: int, o: int) -> int:
    l = u32(l)
    o &= 31
    if o == 0:
        return l
    return u32((l << o) | (l >> (32 - o)))

def Af(l: str) -> int:
    o = u32(_f[0])
    for e, ch in enumerate(l):
        o = ps(u32(o ^ imul(ord(ch), Hl[e & 15])), 5)
    return ci(o)

def wf(l: str):
    o = list(range(256))
    e = 0
    for i in range(256):
        e = (e + o[i] + ord(l[i % len(l)])) & 255
        o[i], o[e] = o[e], o[i]
    return o

def vf(l: str) -> int:
    o = 2166136261
    for ch in l:
        o = u32(imul(o ^ ord(ch), 16777619))
    return ci(o)

def Nf(l: int, o: int, e: int) -> int:
    return u32((l ^ o) | (l & o & e))

class State:
    def __init__(self, S, acc):
        self.S = S
        self.acc = acc

def Rf(l: str, o: int) -> State:
    if If(len(l)):
        return State(wf(l), Af(l))
    e_dict = {}
    i = ci(vf(l) ^ ci(u32(o ^ ms)))
    for r in range(Sf):
        if bf(r):
            n = i % Js
            i = ps(u32(i + ms), 7 + (r & 7))
            e_dict[n] = u32(i ^ ci(i))
            i = ci(u32(i + n))
        else:
            e_dict[r] = Hl[r & 15]
    return State(e_dict, ci(i ^ 2779096485))

def Cf(state: State, o: int) -> int:
    e = state.S
    i = state.acc
    r = i % Js
    n = 0 - (1 if r in e else 0)
    u = u32(e.get(r, 0))
    d = u32(imul(ms, o + 1))
    g = Nf(i, u32(u ^ d), n)
    g = u32(ps(u32(g + i), r & 31) ^ ps(i, (imul(r, 7) & 31)))
    i = ci(u32(g + ms))
    e[r] = u32(i)
    state.acc = i
    return u32(i)

def xf(l: str, o: int, length: int) -> bytearray:
    state = Rf(l, o)
    r = bytearray(length)
    u = 0
    n = 0
    while u < length:
        d = Cf(state, n)
        n += 1
        r[u] = d & 255
        u += 1
        if u < length:
            r[u] = (d >> 8) & 255
            u += 1
        if u < length:
            r[u] = (d >> 16) & 255
            u += 1
        if u < length:
            r[u] = (d >> 24) & 255
            u += 1
    return r

def Df(l: str) -> bytearray:
    rem = len(l) % 4
    if rem > 0:
        l += "=" * (4 - rem)
    l = l.replace("-", "+").replace("_", "/")
    return bytearray(base64.b64decode(l))

def Pf(ciphertext: str, seed: str, tmdb_id: int) -> str:
    i = Df(ciphertext)
    r = xf(seed, tmdb_id, len(i))
    for n in range(len(i)):
        i[n] ^= r[n]
    for n in range(len(Ys)):
        if i[n] != Ys[n]:
            raise ValueError(f"decrypt failed: header byte mismatch {i[:4]} vs {Ys}")
    return i[len(Ys):].decode("utf-8")

client = httpx.Client(
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.vidking.net/",
        "Origin": "https://www.vidking.net"
    },
    timeout=httpx.Timeout(10.0, connect=4.0)
)

tmdb_id = 550
seed_res = client.get(f"https://api.speedracelight.com/seed?mediaId={tmdb_id}")
seed = seed_res.json()["seed"]
print(f"Got seed: {seed}", flush=True)

params = {
    "title": "Fight Club",
    "mediaType": "movie",
    "year": "1999",
    "episodeId": "1",
    "seasonId": "1",
    "tmdbId": str(tmdb_id),
    "imdbId": "tt0137523",
    "enc": "2",
    "seed": seed,
    "_t": str(int(time.time() * 1000))
}

endpoints = [
    ("Yoru", "cdn/sources-with-title"),
    ("Cypher", "downloader2/sources-with-title"),
    ("Neon", "vsrc/sources-with-title"),
]

for name, ep in endpoints:
    print(f"\nRequesting {name} ({ep})...", flush=True)
    res = client.get(f"https://api.speedracelight.com/{ep}", params=params)
    print("Status:", res.status_code, "len:", len(res.text), flush=True)
    if res.status_code == 200:
        try:
            decrypted = Pf(res.text.strip(), seed, tmdb_id)
            data = json.loads(decrypted)
            print("Successfully decrypted!", flush=True)
            print("Data:", json.dumps(data, indent=2)[:500], flush=True)
        except Exception as e:
            print("Decrypt error:", e, flush=True)
