import urllib.request

url = 'https://embed14.streamc.xyz/player.js?ver=1.8'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(req).read().decode('utf-8')

pos = html.find('decryptM3U8')
if pos != -1:
    print(html[pos+1000:pos+3500])
