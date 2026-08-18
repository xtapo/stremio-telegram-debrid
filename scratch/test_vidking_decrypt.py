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
    return u32((a & 0xFFFFFFFF) * (b & 0xFFFFFFFF))

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
    e = [0] * Js
    # note: in js e is a sparse array / object. All unassigned indices are in range 0..Js-1
    # but in JS `r in e` checks if property exists.
    # In JS: const e = new Array(Js); (empty array of size Js)
    # When r is set, e[n] is assigned.
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
            raise ValueError("decrypt failed: bad seed or tampered payload")
    return i[len(Ys):].decode("utf-8")

def test():
    # Test with TMDB 550 (Fight Club)
    tmdb_id = 550
    client = httpx.Client(
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://www.vidking.net/",
            "Origin": "https://www.vidking.net"
        },
        timeout=15.0
    )
    
    # 1. Fetch seed
    seed_res = client.get(f"https://api.speedracelight.com/seed?mediaId={tmdb_id}")
    print("Seed status:", seed_res.status_code)
    seed_data = seed_res.json()
    seed = seed_data["seed"]
    print("Seed:", seed)
    
    # 2. Fetch metadata from db.speedracelight.com (TMDB proxy)
    meta_res = client.get(f"https://db.speedracelight.com/3/movie/{tmdb_id}?append_to_response=external_ids")
    meta = meta_res.json()
    title = meta.get("title", "")
    year = meta.get("release_date", "")[:4]
    imdb_id = meta.get("external_ids", {}).get("imdb_id", "")
    print(f"Meta: title='{title}', year='{year}', imdb='{imdb_id}'")
    
    # 3. Test each server
    servers = {
        "Yoru": "cdn/sources-with-title",
        "Cypher": "downloader2/sources-with-title",
        "Breach": "m4uhd/sources-with-title",
        "Neon": "vsrc/sources-with-title",
        "Vyse": "hdmovie/sources-with-title",
        "Killjoy": "meine/sources-with-title",
        "Fade": "hdmovie/sources-with-title",
        "Omen": "lamovie/sources-with-title",
        "Raze": "superflix/sources-with-title",
    }
    
    for s_name, endpoint in servers.items():
        params = {
            "title": title,
            "mediaType": "movie",
            "year": str(year),
            "episodeId": "1",
            "seasonId": "1",
            "tmdbId": str(tmdb_id),
            "imdbId": imdb_id,
            "enc": "2",
            "seed": seed,
            "_t": str(int(time.time() * 1000))
        }
        if s_name == "Killjoy":
            params["language"] = "german"
            
        url = f"https://api.speedracelight.com/{endpoint}"
        print(f"\n--- Testing {s_name} ---")
        try:
            r = client.get(url, params=params)
            print("Status:", r.status_code)
            if r.status_code == 200:
                raw = r.text.strip()
                print("Raw response len:", len(raw))
                decrypted = Pf(raw, seed, tmdb_id)
                parsed = json.loads(decrypted)
                print("Decrypted JSON keys:", list(parsed.keys()))
                if "sources" in parsed:
                    print("Sources count:", len(parsed["sources"]))
                    for s in parsed["sources"][:3]:
                        print("  Source:", s.get("quality"), s.get("type"), s.get("url")[:80] if s.get("url") else None)
                if "subtitles" in parsed:
                    print("Subtitles count:", len(parsed["subtitles"]))
            else:
                print("Error body:", r.text[:200])
        except Exception as e:
            print("Exception:", e)

if __name__ == '__main__':
    test()
