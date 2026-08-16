import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import httpx
from config import Config

async def list_models():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={Config.GEMINI_API_KEY}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        print("Status:", resp.status_code)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            for m in models:
                if "generateContent" in m.get("supportedGenerationMethods", []):
                    print(" -", m.get("name"))
        else:
            print("Response:", resp.text)

if __name__ == '__main__':
    asyncio.run(list_models())
