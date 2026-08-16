"""
Automatic Vietnamese translation service for movie descriptions and metadata.
"""

import asyncio
import hashlib
import json
import logging
import os
import tempfile
import urllib.parse
from typing import Optional

import httpx

try:
    from config import Config
except ImportError:
    Config = None

logger = logging.getLogger("translation_service")

VIETNAMESE_VOWELS = set("àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ")
CACHE_FILE = os.path.join(tempfile.gettempdir(), "stremio_synopsis_translations.json")
_CACHE = {}


def _load_cache():
    global _CACHE
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _CACHE = json.load(f)
        except Exception:
            _CACHE = {}


def _save_cache_sync():
    try:
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_CACHE, f, ensure_ascii=False)
        os.replace(tmp, CACHE_FILE)
    except Exception:
        pass


_load_cache()


def is_vietnamese(text: str) -> bool:
    if not text:
        return True
    count = sum(1 for ch in text if ch in VIETNAMESE_VOWELS)
    return count >= 3


async def translate_to_vietnamese(text: str) -> str:
    """Translates any movie synopsis/description to natural Vietnamese."""
    if not text or len(text.strip()) < 5:
        return text
    if is_vietnamese(text):
        return text

    cache_key = hashlib.md5(text.strip().encode("utf-8")).hexdigest()
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    # 1. Try MyMemory API (Fast, free, high quality)
    try:
        url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(text[:500])}&langpair=en|vi"
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                translated = data.get("responseData", {}).get("translatedText")
                if translated and not translated.startswith("MYMEMORY WARNING"):
                    _CACHE[cache_key] = translated
                    _save_cache_sync()
                    return translated
    except Exception as e:
        logger.debug(f"MyMemory translation failed: {e}")

    # 2. Try Gemini AI if configured
    if Config and getattr(Config, "ENABLE_GEMINI", False) and getattr(Config, "GEMINI_API_KEY", ""):
        try:
            from subtitle_utils import get_gemini_endpoint
            gemini_url = get_gemini_endpoint(Config.GEMINI_API_KEY)
            prompt = f"Dịch đoạn tóm tắt phim sau sang tiếng Việt một cách tự nhiên và hấp dẫn. Chỉ trả về nội dung tiếng Việt dịch được:\n\n{text}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.post(gemini_url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    translated = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if translated:
                        _CACHE[cache_key] = translated
                        _save_cache_sync()
                        return translated
        except Exception as e:
            logger.debug(f"Gemini translation failed: {e}")

    # 3. Try Lingva API instances
    lingva_instances = [
        "https://lingva.ml",
        "https://lingva.garudalinux.org",
        "https://translate.plausibility.cloud",
    ]
    for inst in lingva_instances:
        try:
            url = f"{inst}/api/v1/auto/vi/{urllib.parse.quote(text[:500])}"
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    translated = resp.json().get("translation")
                    if translated:
                        _CACHE[cache_key] = translated
                        _save_cache_sync()
                        return translated
        except Exception:
            continue

    return text
