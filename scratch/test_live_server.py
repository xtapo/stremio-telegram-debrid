import urllib.request
import json

try:
    req = urllib.request.Request("http://127.0.0.1:7860/ernax/manifest.json")
    res = urllib.request.urlopen(req, timeout=5)
    print("Live Server Manifest Status:", res.status)
    data = json.loads(res.read().decode("utf-8"))
    print("Live Server Manifest Name:", data.get("name"))
except Exception as e:
    print("Live server test failed:", e)

try:
    req2 = urllib.request.Request("http://127.0.0.1:7860/ernax/stream/movie/ernax:movie:550.json")
    res2 = urllib.request.urlopen(req2, timeout=10)
    print("Live Server Stream Status:", res2.status)
    streams = json.loads(res2.read().decode("utf-8")).get("streams", [])
    print("Live Server Stream Count:", len(streams))
    if streams and streams[1].get("url"):
        test_stream = streams[1].get("url")
        print("Testing live playback of:", test_stream[:80])
        r3 = urllib.request.urlopen(test_stream, timeout=10)
        print("Live Stream Playlist Status:", r3.status, "bytes:", len(r3.read()))
except Exception as e:
    print("Live stream test failed:", e)
