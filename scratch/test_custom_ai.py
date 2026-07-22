import asyncio
import httpx
import json

class Config:
    CUSTOM_AI_API_KEY = "sk-a86871a871e9d5e8-3we7a5-db528d34"
    CUSTOM_AI_API_URL = "https://ai.xtapo.org/v1"
    CUSTOM_AI_MODEL = "jamid"
    CUSTOM_AI_STREAM = True

async def translate_custom_ai(text: str, target_lang: str = "vi") -> str:
    url = Config.CUSTOM_AI_API_URL.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    api_key = Config.CUSTOM_AI_API_KEY
    model = Config.CUSTOM_AI_MODEL
    stream_mode = Config.CUSTOM_AI_STREAM
    
    prompt = (
        f"Translate the following subtitles into natural, conversational Vietnamese. "
        f"Keep all timestamps, line numbers, and formatting exactly as they are. "
        f"Output only the translated SRT subtitles and nothing else:\n\n{text}"
    )
    
    headers = {
        "Content-Type": "application/json"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": stream_mode
    }
    
    translated_text = ""
    async with httpx.AsyncClient(timeout=60.0) as client:
        if stream_mode:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                print("Status code (stream):", response.status_code)
                if response.status_code != 200:
                    err_content = await response.aread()
                    raise Exception(f"Custom AI API status {response.status_code}: {err_content.decode('utf-8', errors='ignore')}")
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data_json = json.loads(data_str)
                            content = data_json["choices"][0]["delta"].get("content", "")
                            translated_text += content
                        except Exception as e:
                            pass
        else:
            response = await client.post(url, json=payload, headers=headers)
            print("Status code (non-stream):", response.status_code)
            if response.status_code != 200:
                raise Exception(f"Custom AI API status {response.status_code}: {response.text}")
            data_json = response.json()
            try:
                translated_text = data_json["choices"][0]["message"]["content"]
            except (KeyError, IndexError):
                raise Exception("Invalid Custom AI API response structure (non-streaming)")
                
    return translated_text.strip()

async def main():
    test_srt = "1\n00:00:01,000 --> 00:00:04,000\nHello, how are you?\n\n2\n00:00:05,000 --> 00:00:08,000\nI am fine, thank you."
    try:
        print("Testing Custom AI translation...")
        res = await translate_custom_ai(test_srt)
        print("\n--- Result ---")
        print(res.encode("utf-8", errors="ignore"))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
