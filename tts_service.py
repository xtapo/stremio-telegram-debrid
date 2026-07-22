import os
import re
import json
import httpx
import hashlib
import asyncio
import logging
import shutil
import tempfile
import urllib.parse
import array
from config import Config
from subtitles_service import parse_subtitles

logger = logging.getLogger("tts_service")

# Setup caching directories (in temp dir to prevent Uvicorn restart loops)
CACHE_DIR = os.path.join(tempfile.gettempdir(), "stremio_telegram_tts")
os.makedirs(CACHE_DIR, exist_ok=True)

class TTSServiceManager:
    def __init__(self):
        self.active_tasks = {}

    def get_ffmpeg_path(self) -> str:
        # Check workspace root first, then system PATH
        local_ffmpeg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffmpeg.exe")
        if os.path.exists(local_ffmpeg):
            return local_ffmpeg
        return shutil.which("ffmpeg") or "ffmpeg"

    async def get_pcm_for_text(self, text: str) -> bytes:
        """
        Generates TTS for a line of text, converts to PCM (24000Hz, 16-bit, mono), and caches it.
        """
        text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        pcm_path = os.path.join(CACHE_DIR, f"{text_hash}.pcm")
        
        # 1. Return cached PCM if it exists
        if os.path.exists(pcm_path):
            try:
                with open(pcm_path, "rb") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Failed to read cached PCM file '{pcm_path}': {e}")

        # 2. Generate MP3 if not already done
        mp3_path = os.path.join(CACHE_DIR, f"{text_hash}.mp3")
        generated = False
        
        # Try edge-tts first
        if not os.path.exists(mp3_path):
            try:
                import edge_tts
                communicate = edge_tts.Communicate(text, "vi-VN-HoaiMyNeural")
                await communicate.save(mp3_path)
                generated = True
            except ImportError:
                logger.warning("edge-tts is not installed. Falling back to Google Translate TTS.")
            except Exception as e:
                logger.warning(f"edge-tts generation failed: {e}. Falling back to Google Translate TTS.")
            
            # Fallback to Google Translate TTS
            if not generated:
                try:
                    url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl=vi&client=tw-ob&q={urllib.parse.quote(text)}"
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.get(url)
                        if resp.status_code == 200:
                            with open(mp3_path, "wb") as f:
                                f.write(resp.content)
                            generated = True
                        else:
                            logger.error(f"Google TTS returned status {resp.status_code}")
                except Exception as ex:
                    logger.error(f"Google TTS request failed: {ex}")

        if not os.path.exists(mp3_path):
            return b""

        # 3. Convert MP3 to raw PCM (24000Hz, 16-bit, mono) via ffmpeg
        ffmpeg_path = self.get_ffmpeg_path()
        cmd = [
            ffmpeg_path, "-y",
            "-i", mp3_path,
            "-f", "s16le",
            "-acodec", "pcm_s16le",
            "-ar", "24000",
            "-ac", "1",
            pcm_path
        ]
        
        try:
            import subprocess
            await asyncio.to_thread(
                subprocess.run,
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Read PCM and clean up MP3
            if os.path.exists(pcm_path):
                with open(pcm_path, "rb") as f:
                    pcm_data = f.read()
                try:
                    os.remove(mp3_path)
                except Exception:
                    pass
                return pcm_data
        except Exception as e:
            logger.error(f"ffmpeg conversion failed: {e}", exc_info=True)
            
        return b""

    async def start_tts_generation(self, cache_key: str, srt_content: str):
        """
        Triggers pre-generation of Vietnamese TTS audio in the background.
        """
        if not Config.AUTO_THUYET_MINH:
            return
            
        if cache_key in self.active_tasks:
            return
            
        self.active_tasks[cache_key] = asyncio.create_task(
            self._run_tts_pregeneration(cache_key, srt_content)
        )

    async def _run_tts_pregeneration(self, cache_key: str, srt_content: str):
        logger.info(f"Starting background TTS generation for {cache_key}...")
        final_pcm_path = os.path.join(CACHE_DIR, f"{cache_key}_merged.pcm")
        
        if os.path.exists(final_pcm_path):
            logger.info(f"Merged TTS PCM already exists for {cache_key}.")
            if cache_key in self.active_tasks:
                del self.active_tasks[cache_key]
            return

        try:
            header, blocks = parse_subtitles(srt_content)
            
            # Clean and prepare blocks
            cleaned_blocks = []
            for b in blocks:
                text = b["text"].strip()
                # Remove HTML tags (e.g. <b>, <i>, <font>)
                text = re.sub(r'<[^>]*>', '', text).strip()
                
                # Ignore empty text or technical banner lines
                if not text or (text.startswith("[") and text.endswith("]")) or (text.startswith("(") and text.endswith(")")):
                    continue
                if "tiến trình dịch" in text.lower() or "phụ đề được" in text.lower():
                    continue
                    
                parts = b["time"].split("-->")
                if len(parts) == 2:
                    start_str = parts[0].strip().replace(",", ".")
                    try:
                        t_parts = start_str.split(":")
                        if len(t_parts) == 3:
                            h, m, s = t_parts
                            t_start = float(h) * 3600 + float(m) * 60 + float(s)
                        elif len(t_parts) == 2:
                            m, s = t_parts
                            t_start = float(m) * 60 + float(s)
                        else:
                            t_start = float(start_str)
                    except ValueError:
                        continue
                    cleaned_blocks.append((t_start, text))

            if not cleaned_blocks:
                logger.warning(f"No valid subtitle lines to translate to TTS for {cache_key}.")
                return

            # Fetch/generate PCM chunks with controlled concurrency
            sem = asyncio.Semaphore(10)
            
            async def process_block(t_start, t_text):
                async with sem:
                    pcm_data = await self.get_pcm_for_text(t_text)
                    return t_start, pcm_data

            tasks = [process_block(t_start, text) for t_start, text in cleaned_blocks]
            results = await asyncio.gather(*tasks)

            # Mix chunks into a single large PCM array
            max_time = max(t_start for t_start, _ in cleaned_blocks)
            total_seconds = int(max_time + 60) # pad 60 seconds
            total_samples = total_seconds * 24000
            
            logger.info(f"Allocating array of size {total_samples} samples (~{total_seconds}s) for {cache_key}...")
            pcm_array = array.array('h', [0] * total_samples)

            for t_start, pcm_data in results:
                if not pcm_data:
                    continue
                
                start_sample = int(t_start * 24000)
                chunk_array = array.array('h')
                chunk_array.frombytes(pcm_data)
                
                # Overlay mixed audio with clipping guard
                for idx, sample in enumerate(chunk_array):
                    pos = start_sample + idx
                    if pos < len(pcm_array):
                        mixed = pcm_array[pos] + sample
                        if mixed > 32767:
                            mixed = 32767
                        elif mixed < -32768:
                            mixed = -32768
                        pcm_array[pos] = mixed

            # Save the merged PCM output
            with open(final_pcm_path, "wb") as f:
                f.write(pcm_array.tobytes())
            
            logger.info(f"Successfully finished background TTS generation for {cache_key} at: {final_pcm_path}")
        except Exception as e:
            logger.error(f"Error in background TTS generation for {cache_key}: {e}")
        finally:
            if cache_key in self.active_tasks:
                del self.active_tasks[cache_key]

# Export singleton
tts_manager = TTSServiceManager()
