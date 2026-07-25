import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# 1. Fetch genre list to get codes
res_g = requests.get("https://topxx.vip/api/v1/genres", headers=headers)
genres = res_g.json().get("data", [])

print(f"Total genres: {len(genres)}")
for g in genres[:5]:
    code = g.get("code")
    slug = g.get("slug")
    names = [t.get("name") for t in g.get("translations", [])]
    
    # Test page 1 & page 2 for this genre
    url_p1 = f"https://topxx.vip/api/v1/genres/{code}/movies?page=1"
    url_p2 = f"https://topxx.vip/api/v1/genres/{code}/movies?page=2"
    
    res1 = requests.get(url_p1, headers=headers).json()
    res2 = requests.get(url_p2, headers=headers).json()
    
    data1 = res1.get("data", [])
    data2 = res2.get("data", [])
    meta1 = res1.get("meta", {})
    
    print(f"\nGenre '{names}' (code: {code}):")
    print(f"  Page 1 items count: {len(data1)}")
    print(f"  Page 2 items count: {len(data2)}")
    print(f"  Meta object: {meta1}")
    if data1 and data2:
        print(f"  Page 1 first title: {data1[0]['trans'][0]['title'] if data1[0].get('trans') else ''}")
        print(f"  Page 2 first title: {data2[0]['trans'][0]['title'] if data2[0].get('trans') else ''}")

# 2. Fetch country list to get codes
res_c = requests.get("https://topxx.vip/api/v1/countries", headers=headers)
countries = res_c.json().get("data", [])
print(f"\nTotal countries: {len(countries)}")
for c in countries[:3]:
    code = c.get("code")
    names = [t.get("name") for t in c.get("translations", [])]
    
    url_p1 = f"https://topxx.vip/api/v1/countries/{code}/movies?page=1"
    url_p2 = f"https://topxx.vip/api/v1/countries/{code}/movies?page=2"
    
    res1 = requests.get(url_p1, headers=headers).json()
    res2 = requests.get(url_p2, headers=headers).json()
    
    data1 = res1.get("data", [])
    data2 = res2.get("data", [])
    meta1 = res1.get("meta", {})
    
    print(f"\nCountry '{names}' (code: {code}):")
    print(f"  Page 1 items count: {len(data1)}")
    print(f"  Page 2 items count: {len(data2)}")
    print(f"  Meta object: {meta1}")
