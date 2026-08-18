import httpx

client = httpx.Client(timeout=10.0)
r = client.get("http://127.0.0.1:7860/hdtoday/stream_proxy")
print("Status without route:", r.status_code)
