import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import httpx

async def test_post():
    text = "Hello world! This is a test."
    async with httpx.AsyncClient() as client:
        # Try POST to lingva
        resp = await client.post("https://lingva.ml/api/v1/auto/vi", data={"query": text})
        print("POST to lingva.ml status:", resp.status_code)
        if resp.status_code == 200:
            print("POST result:", resp.json())
        else:
            print("POST body:", resp.text)

if __name__ == '__main__':
    asyncio.run(test_post())
