import os
import io
import re
import json
import zipfile
import urllib.request

plugins = [
    "KKPhim", "RidoMovies", "Anime47", "Animevietsub", "Animehay", "Animet",
    "AnimeKai", "BluPhim", "CLBPhimXua", "HDVNN", "HoatHinh3D", "Onflix",
    "PhimDinhCao", "PhimHDCS", "PhimSea", "VSMOV", "Yanhh3d", "YumeiAnime"
]

for name in plugins:
    url = f"https://0cs3.onii.pp.ua/movie/{name}.cs3"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = urllib.request.urlopen(req).read()
        zf = zipfile.ZipFile(io.BytesIO(data))
        dex = zf.read('classes.dex')
        
        raw_strings = re.findall(rb'[\x20-\x7e]{3,}', dex)
        strings = [s.decode('ascii', errors='ignore') for s in raw_strings]
        
        # Filter interesting strings
        interesting = [s for s in strings if any(k in s for k in [
            'http', 'api', 'search', 'player', 'embed', 'm3u8', 'v1', 'v2', 'slug', 'wp-json',
            'token', 'key', 'eval', 'document', 'iframe', 'json', 'stream'
        ]) and not any(x in s for x in ['com/lagradost', 'com/fasterxml', 'okhttp3', 'kotlin/'])]
        
        print(f"\n==================== {name} ====================")
        for s in interesting[:25]:
            print(f"  {s}")
            
        with open(f"scratch/{name}_strings.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(strings))
    except Exception as e:
        print(f"Error {name}: {e}")
