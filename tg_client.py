import os
import time
import logging
import asyncio

# Fix Pyrogram event loop crash on Python 3.10+ / 3.12 / 3.14
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import functools
import inspect
import re
import collections
from hashlib import sha256
from typing import Callable, Optional, AsyncGenerator, Union, List, Dict

from pyrogram import Client, raw, utils
from pyrogram.types import Message
from pyrogram.session.auth import Auth
from pyrogram.session import Session
from pyrogram.file_id import FileId, FileType, ThumbnailSource
from pyrogram.errors import VolumeLocNotFound, CDNFileHashMismatch, FloodWait, FileReferenceExpired
from pyrogram.crypto import aes
import pyrogram
from config import Config
from utils import parse_split_info

logger = logging.getLogger("tg_client")


# Media chunk caching manager (LRU cache of AsyncIO Tasks)
class ChunkCache:
    def __init__(self, max_size_mb: int):
        self.max_size = max_size_mb
        self.cache = collections.OrderedDict()  # key -> asyncio.Task yielding bytes
        self.lock = asyncio.Lock()

    async def get_or_create(self, key, download_coro_fn):
        async with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]

            async def wrapper():
                try:
                    return await download_coro_fn()
                except Exception as e:
                    async with self.lock:
                        self.cache.pop(key, None)
                    raise e

            task = asyncio.create_task(wrapper())
            self.cache[key] = task

            if len(self.cache) > self.max_size:
                old_key, old_task = self.cache.popitem(last=False)
                if not old_task.done():
                    old_task.cancel()

            return task

    async def exists(self, key) -> bool:
        async with self.lock:
            return key in self.cache

chunk_cache = ChunkCache(Config.STREAM_CACHE_SIZE_MB)

# File-level cache for CDN redirect info
_file_cdn_info = {}
_file_cdn_lock = asyncio.Lock()

# Map media_id -> set of client ids incompatible with that media's file reference
_media_incompatible_workers = collections.defaultdict(set)


async def _get_media_session(client: Client, dc_id: int) -> Session:
    """Get or create standard, robust MTProto media session for a specific client and DC."""
    async with client.media_sessions_lock:
        session = client.media_sessions.get(dc_id)
        if session is not None:
            return session

        worker_name = getattr(client, "name", "worker")
        logger.info(f"[{worker_name}] Initializing MTProto media session for DC{dc_id}...")
        session = Session(
            client, dc_id,
            await Auth(client, dc_id, await client.storage.test_mode()).create()
            if dc_id != await client.storage.dc_id()
            else await client.storage.auth_key(),
            await client.storage.test_mode(),
            is_media=True
        )
        await session.start()

        if dc_id != await client.storage.dc_id():
            exported_auth = await client.invoke(
                raw.functions.auth.ExportAuthorization(dc_id=dc_id)
            )
            await session.invoke(
                raw.functions.auth.ImportAuthorization(
                    id=exported_auth.id,
                    bytes=exported_auth.bytes
                )
            )

        client.media_sessions[dc_id] = session
        return session


async def _download_cdn_block(session, cdn_session, r, offset_bytes, chunk_size) -> bytes:
    while True:
        r2 = await cdn_session.invoke(
            raw.functions.upload.GetCdnFile(
                file_token=r.file_token,
                offset=offset_bytes,
                limit=chunk_size
            )
        )

        if isinstance(r2, raw.types.upload.CdnFileReuploadNeeded):
            try:
                await session.invoke(
                    raw.functions.upload.ReuploadCdnFile(
                        file_token=r.file_token,
                        request_token=r2.request_token
                    )
                )
            except VolumeLocNotFound:
                return b""
            else:
                continue

        chunk = r2.bytes

        decrypted_chunk = aes.ctr256_decrypt(
            chunk,
            r.encryption_key,
            bytearray(
                r.encryption_iv[:-4]
                + (offset_bytes // 16).to_bytes(4, "big")
            )
        )

        hashes = await session.invoke(
            raw.functions.upload.GetCdnFileHashes(
                file_token=r.file_token,
                offset=offset_bytes
            )
        )

        for i, h in enumerate(hashes):
            cdn_chunk = decrypted_chunk[h.limit * i: h.limit * (i + 1)]
            CDNFileHashMismatch.check(
                h.hash == sha256(cdn_chunk).digest(),
                "h.hash == sha256(cdn_chunk).digest()"
            )

        return decrypted_chunk


async def _fetch_block_from_tg(
    file_id: FileId,
    location,
    dc_id: int,
    offset_bytes: int,
    chunk_size: int,
    file_size: int,
    preferred_client: Optional[Client] = None
) -> bytes:
    """Fetch a media chunk from Telegram with Multi-Client Load Balancing & Failover."""
    media_id = file_id.media_id

    # Get available workers sorted for round-robin load distribution
    workers = tg_client_manager.get_available_workers(
        chunk_offset=offset_bytes,
        preferred=preferred_client,
        media_id=media_id
    )

    last_error = None
    has_multiple_workers = len(workers) > 1

    for client in workers:
        worker_name = getattr(client, "name", "worker")
        try:
            session = await _get_media_session(client, dc_id)

            # 1. Check if CDN file
            async with _file_cdn_lock:
                cdn_info = _file_cdn_info.get(media_id)

            if cdn_info and cdn_info.get("is_cdn"):
                cdn_session = cdn_info["cdn_session"]
                r = cdn_info["redirect_info"]
                return await _download_cdn_block(session, cdn_session, r, offset_bytes, chunk_size)

            # 2. Standard GetFile request
            sleep_thresh = 0 if has_multiple_workers else 30
            try:
                r = await session.invoke(
                    raw.functions.upload.GetFile(
                        location=location,
                        offset=offset_bytes,
                        limit=chunk_size
                    ),
                    sleep_threshold=sleep_thresh
                )
            except FloodWait as fw:
                if has_multiple_workers:
                    logger.warning(
                        f"[{worker_name}] Got FloodWait({fw.value}s) at offset {offset_bytes}. "
                        f"Failing over to next worker in pool..."
                    )
                    tg_client_manager.report_flood_wait(client, fw.value)
                    continue
                else:
                    logger.warning(f"[{worker_name}] Waiting {fw.value}s for FloodWait...")
                    await asyncio.sleep(fw.value)
                    r = await session.invoke(
                        raw.functions.upload.GetFile(
                            location=location,
                            offset=offset_bytes,
                            limit=chunk_size
                        ),
                        sleep_threshold=30
                    )
            except FileReferenceExpired:
                # File reference is account-specific (e.g. user session vs bot token)
                logger.info(
                    f"[{worker_name}] Cannot use file_reference on media {media_id} (FILE_REFERENCE_EXPIRED). "
                    f"Routing to primary client..."
                )
                _media_incompatible_workers[media_id].add(id(client))
                continue
            except Exception as e:
                # Connection or MTProto session error - purge from client map so it reconnects on next try
                logger.warning(f"[{worker_name}] Error in media session for DC{dc_id}: {e}")
                async with client.media_sessions_lock:
                    if client.media_sessions.get(dc_id) is session:
                        client.media_sessions.pop(dc_id, None)
                try:
                    await session.stop()
                except Exception:
                    pass
                last_error = e
                continue

            if isinstance(r, raw.types.upload.File):
                return r.bytes

            elif isinstance(r, raw.types.upload.FileCdnRedirect):
                logger.info(f"[{worker_name}] FileCdnRedirect encountered for media {media_id}. Setting up CDN session...")
                async with _file_cdn_lock:
                    cdn_info = _file_cdn_info.get(media_id)
                    if not cdn_info:
                        cdn_session = Session(
                            client, r.dc_id, await Auth(client, r.dc_id, await client.storage.test_mode()).create(),
                            await client.storage.test_mode(), is_media=True, is_cdn=True
                        )
                        await cdn_session.start()
                        cdn_info = {
                            "is_cdn": True,
                            "cdn_session": cdn_session,
                            "redirect_info": r
                        }
                        _file_cdn_info[media_id] = cdn_info
                    else:
                        cdn_session = cdn_info["cdn_session"]
                        r = cdn_info["redirect_info"]

                return await _download_cdn_block(session, cdn_session, r, offset_bytes, chunk_size)

            return b""

        except Exception as e:
            last_error = e
            continue

    if last_error:
        logger.error(f"All workers failed to stream block at offset {offset_bytes} for media {media_id}: {last_error}")
        raise last_error

    return b""


# Monkey-patch Client.get_file to reuse media sessions and avoid connection overhead
async def _patched_get_file(
    self: Client,
    file_id: FileId,
    file_size: int = 0,
    limit: int = 0,
    offset: int = 0,
    progress: Callable = None,
    progress_args: tuple = ()
) -> Optional[AsyncGenerator[bytes, None]]:
    async with self.get_file_semaphore:
        file_type = file_id.file_type

        if file_type == FileType.CHAT_PHOTO:
            if file_id.chat_id > 0:
                peer = raw.types.InputPeerUser(
                    user_id=file_id.chat_id,
                    access_hash=file_id.chat_access_hash
                )
            else:
                if file_id.chat_access_hash == 0:
                    peer = raw.types.InputPeerChat(
                        chat_id=-file_id.chat_id
                    )
                else:
                    peer = raw.types.InputPeerChannel(
                        channel_id=utils.get_channel_id(file_id.chat_id),
                        access_hash=file_id.chat_access_hash
                    )

            location = raw.types.InputPeerPhotoFileLocation(
                peer=peer,
                photo_id=file_id.media_id,
                big=file_id.thumbnail_source == ThumbnailSource.CHAT_PHOTO_BIG
            )
        elif file_type == FileType.PHOTO:
            location = raw.types.InputPhotoFileLocation(
                id=file_id.media_id,
                access_hash=file_id.access_hash,
                file_reference=file_id.file_reference,
                thumb_size=file_id.thumbnail_size
            )
        else:
            location = raw.types.InputDocumentFileLocation(
                id=file_id.media_id,
                access_hash=file_id.access_hash,
                file_reference=file_id.file_reference,
                thumb_size=file_id.thumbnail_size
            )

        current = 0
        total = abs(limit) or (1 << 31) - 1
        chunk_size = 1024 * 1024
        offset_bytes = abs(offset) * chunk_size
        dc_id = file_id.dc_id
        media_id = file_id.media_id

        while True:
            key = (media_id, file_id.thumbnail_size or "", offset_bytes)

            # 1. Get or create download task for the current chunk (dispatched to worker pool)
            curr_off = offset_bytes
            download_coro_fn = lambda off=curr_off: _fetch_block_from_tg(
                file_id, location, dc_id, off, chunk_size, file_size, preferred_client=self
            )
            task = await chunk_cache.get_or_create(key, download_coro_fn)

            # 2. Trigger pre-fetching for next chunks in the background
            for i in range(1, Config.PREFETCH_CHUNKS + 1):
                next_offset = offset_bytes + i * chunk_size
                if file_size > 0 and next_offset >= file_size:
                    break

                next_key = (media_id, file_id.thumbnail_size or "", next_offset)
                if not await chunk_cache.exists(next_key):
                    next_coro_fn = lambda off=next_offset: _fetch_block_from_tg(
                        file_id, location, dc_id, off, chunk_size, file_size, preferred_client=self
                    )
                    await chunk_cache.get_or_create(next_key, next_coro_fn)

            # 3. Await current chunk
            try:
                chunk = await task
            except Exception as e:
                logger.error(f"Failed to stream block at offset {offset_bytes} for media {media_id}: {e}")
                raise e

            if not chunk:
                break

            yield chunk

            current += 1
            offset_bytes += chunk_size

            if progress:
                func = functools.partial(
                    progress,
                    min(offset_bytes, file_size) if file_size != 0 else offset_bytes,
                    file_size,
                    *progress_args
                )

                if inspect.iscoroutinefunction(progress):
                    await func()
                else:
                    await self.loop.run_in_executor(self.executor, func)

            if len(chunk) < chunk_size or current >= total:
                break

Client.get_file = _patched_get_file


class TelegramClientManager:
    def __init__(self):
        self.client: Optional[Client] = None
        self.workers: List[Client] = []
        self.worker_cooldowns: Dict[int, float] = {}  # id(client) -> timestamp
        self.me = None
        self.is_running = False
        self._search_cache = {}
        self._message_cache = {}
        self._log_cache = {}

    def initialize(self):
        Config.validate()

        # 1. Initialize Primary Client (with live MTProto push updates enabled)
        if Config.USER_SESSION_STRING:
            logger.info("Initializing Primary User Client...")
            self.client = Client(
                name="tg_stremio_user",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                session_string=Config.USER_SESSION_STRING,
                in_memory=True,
                no_updates=False
            )
        elif Config.BOT_TOKEN:
            logger.info("Initializing Primary Bot Client...")
            self.client = Client(
                name="tg_stremio_bot",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                bot_token=Config.BOT_TOKEN,
                in_memory=True,
                no_updates=False
            )
        else:
            raise ValueError("Neither USER_SESSION_STRING nor BOT_TOKEN is configured!")

        self._setup_event_handlers()
        self.workers = [self.client]

    def _setup_event_handlers(self):
        """Register real-time event listeners for instant catalog update when new media is posted."""
        if not self.client:
            return

        @self.client.on_message()
        async def _on_new_message(client, message):
            try:
                chat_id = getattr(message.chat, "id", None)
                if not chat_id:
                    return
                channel_ids = [str(c) for c in self.get_channel_ids()]
                if str(chat_id) in channel_ids:
                    logger.info(f"⚡ [Auto-Sync] New message {message.id} detected in channel {chat_id}! Clearing search cache...")
                    self._search_cache.clear()
                    # Pre-generate thumbnail in background if media present
                    if self._has_media(message):
                        chat_str = str(chat_id)
                        msg_id = message.id
                        thumb_path = os.path.join("temp_cache", "thumbs", f"{chat_str}_{msg_id}.jpg")
                        try:
                            from addon import _process_thumbnail_task
                            asyncio.create_task(_process_thumbnail_task(chat_str, msg_id, thumb_path))
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"Error in on_message handler: {e}")

        @self.client.on_edited_message()
        async def _on_edited(client, message):
            self._search_cache.clear()

        @self.client.on_deleted_messages()
        async def _on_deleted(client, messages):
            self._search_cache.clear()

        # 2. Parse & initialize Extra User Sessions
        extra_sessions_raw = getattr(Config, "EXTRA_SESSION_STRINGS", "") or ""
        extra_sessions = [
            s.strip() for s in re.split(r"[,;\n\r]+", extra_sessions_raw) if s.strip()
        ]
        for idx, s_str in enumerate(extra_sessions, 1):
            if s_str == Config.USER_SESSION_STRING:
                continue
            worker = Client(
                name=f"tg_worker_user_{idx}",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                session_string=s_str,
                in_memory=True,
                no_updates=True
            )
            self.workers.append(worker)

        # 3. Parse & initialize Extra Bot Tokens
        extra_bots_raw = getattr(Config, "EXTRA_BOT_TOKENS", "") or ""
        extra_bots = [
            b.strip() for b in re.split(r"[,;\n\r]+", extra_bots_raw) if b.strip()
        ]
        for idx, b_tok in enumerate(extra_bots, 1):
            if b_tok == Config.BOT_TOKEN:
                continue
            worker = Client(
                name=f"tg_worker_bot_{idx}",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                bot_token=b_tok,
                in_memory=True,
                no_updates=True
            )
            self.workers.append(worker)

        logger.info(
            f"Telegram Worker Pool configured with {len(self.workers)} client(s) "
            f"(1 primary + {len(extra_sessions)} extra user(s) + {len(extra_bots)} extra bot(s))."
        )

    def get_available_workers(self, chunk_offset: int = 0, preferred: Optional[Client] = None, media_id: Optional[int] = None) -> List[Client]:
        """Return list of workers rotated and ordered for round-robin load distribution."""
        now = time.time()

        # Clean expired cooldowns and filter incompatible workers for this media
        incompatible = _media_incompatible_workers.get(media_id, set()) if media_id else set()
        active = [
            w for w in self.workers
            if (now >= self.worker_cooldowns.get(id(w), 0)) and (id(w) not in incompatible)
        ]

        # If all workers are cooling down or filtered, fallback to preferred client or primary client
        if not active:
            if preferred and id(preferred) not in incompatible:
                return [preferred]
            if self.client and id(self.client) not in incompatible:
                return [self.client]
            active = self.workers

        if len(active) <= 1:
            return active

        # Round-robin rotation based on chunk index
        chunk_idx = chunk_offset // (1024 * 1024)
        rot = chunk_idx % len(active)
        rotated = active[rot:] + active[:rot]

        return rotated

    def report_flood_wait(self, client: Client, wait_seconds: float):
        """Put a worker in cooldown due to FloodWait."""
        self.worker_cooldowns[id(client)] = time.time() + wait_seconds + 0.5
        worker_name = getattr(client, "name", "worker")
        logger.warning(f"Worker [{worker_name}] marked in cooldown for {wait_seconds:.1f}s (FloodWait).")

    def get_pool_status(self) -> dict:
        """Return pool health statistics for the dashboard."""
        now = time.time()
        active_count = sum(1 for w in self.workers if now >= self.worker_cooldowns.get(id(w), 0))
        details = []
        for w in self.workers:
            cd_until = self.worker_cooldowns.get(id(w), 0)
            remaining_cd = max(0, cd_until - now)
            details.append({
                "name": getattr(w, "name", "unknown"),
                "is_connected": getattr(w, "is_connected", False),
                "in_cooldown": remaining_cd > 0,
                "cooldown_remaining_sec": round(remaining_cd, 1)
            })
        return {
            "total_workers": len(self.workers),
            "active_workers": active_count,
            "worker_details": details
        }

    def get_channel_ids(self) -> list:
        val = Config.TELEGRAM_CHANNEL_ID
        if not val:
            return []
        if isinstance(val, int):
            return [val]
        parts = [p.strip() for p in str(val).split(",")]
        ids = []
        for p in parts:
            if p.startswith("-") or p.isdigit():
                try:
                    ids.append(int(p))
                except ValueError:
                    ids.append(p)
            else:
                ids.append(p)
        return ids

    async def start(self):
        if not self.client:
            self.initialize()

        if not self.is_running:
            logger.info(f"Starting {len(self.workers)} Pyrogram client worker(s)...")

            # Start all workers concurrently
            start_tasks = []
            for w in self.workers:
                async def _safe_start(worker):
                    try:
                        await worker.start()
                    except Exception as e:
                        logger.error(f"Failed to start worker {getattr(worker, 'name', 'worker')}: {e}")
                start_tasks.append(_safe_start(w))

            await asyncio.gather(*start_tasks)
            self.is_running = True

            try:
                self.me = await self.client.get_me()
            except Exception:
                self.me = None

            # Resolve target channels on startup to avoid PeerIdInvalid errors
            try:
                chat_ids = self.get_channel_ids()

                if Config.USER_SESSION_STRING:
                    cached_count = 0
                    async for dialog in self.client.get_dialogs(limit=400):
                        if dialog.chat.id in chat_ids:
                            logger.info(f"Resolved channel: {dialog.chat.title} ({dialog.chat.id})")
                            cached_count += 1
                            if cached_count >= len(chat_ids):
                                break

                for chat_id in chat_ids:
                    try:
                        await self.client.get_chat(chat_id)
                    except Exception as e:
                        logger.warning(f"Failed to cache channel {chat_id}: {e}")

                if Config.LOG_CHANNEL_ID:
                    try:
                        await self.client.get_chat(Config.LOG_CHANNEL_ID)
                    except Exception as e:
                        logger.warning(f"Failed to cache log channel {Config.LOG_CHANNEL_ID}: {e}")
            except Exception as e:
                logger.warning(f"Failed to resolve target channels on startup: {e}")

    async def stop(self):
        if self.is_running:
            logger.info("Stopping Telegram worker pool...")

            stop_tasks = []
            for w in self.workers:
                if getattr(w, "is_connected", False):
                    stop_tasks.append(asyncio.wait_for(w.stop(), timeout=3.0))

            if stop_tasks:
                results = await asyncio.gather(*stop_tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, Exception):
                        logger.debug(f"Worker stop error/timeout: {r}")

            self.is_running = False

    async def send_play_log(self, filename: str, chat_id: Union[str, int], message_id: int):
        if not Config.LOG_CHANNEL_ID:
            return

        key = (chat_id, message_id)
        now = time.time()

        # Avoid duplicate logs for the same file within 15 mins
        if key in self._log_cache and now - self._log_cache[key] < 900:
            return

        self._log_cache[key] = now

        try:
            import datetime
            from datetime import timezone, timedelta

            tz_str = getattr(Config, "TIMEZONE", "UTC") or "UTC"
            local_dt = None

            try:
                from zoneinfo import ZoneInfo
                local_dt = datetime.datetime.now(ZoneInfo(tz_str))
            except Exception:
                pass

            if local_dt is None:
                try:
                    tz_clean = tz_str.upper().replace("UTC", "").replace("GMT", "").strip()
                    if tz_clean and tz_clean[0] in ("+", "-"):
                        sign = 1 if tz_clean[0] == "+" else -1
                        time_parts = tz_clean[1:].split(":")
                        hours = int(time_parts[0])
                        minutes = int(time_parts[1]) if len(time_parts) > 1 else 0
                        td = timedelta(hours=hours, minutes=minutes)
                        local_dt = datetime.datetime.now(timezone(sign * td))
                except Exception:
                    pass

            if local_dt is None:
                local_dt = datetime.datetime.now(timezone.utc)

            time_str = local_dt.strftime("%Y-%m-%d %H:%M:%S")
            year_str = local_dt.strftime("%Y")

            message_text = (
                f"🎬 **Media Stream Log**\n\n"
                f"📁 **File Name:** `{filename}`\n"
                f"📅 **Date & Time:** `{time_str}`\n"
                f"📆 **Year:** `{year_str}`\n"
                f"💬 **Source Channel:** `{chat_id}`\n"
                f"🆔 **Message ID:** `{message_id}`"
            )

            await self.client.send_message(
                chat_id=Config.LOG_CHANNEL_ID,
                text=message_text
            )
        except Exception as e:
            logger.error(f"Failed to send log to log channel: {e}")

    async def search_messages(self, query: str = "", limit: int = 50):
        if not self.is_running:
            await self.start()

        query_str = str(query).strip() if query else ""

        cache_key = query_str
        now = time.time()
        if cache_key in self._search_cache:
            cached_time, cached_results, fully_fetched = self._search_cache[cache_key]
            if now - cached_time < Config.CACHE_TTL:
                if len(cached_results) >= limit or fully_fetched:
                    logger.info(f"Search cache HIT for query='{query_str}' (limit={limit}, cache_size={len(cached_results)}, fully_fetched={fully_fetched})")
                    return cached_results[:limit]

        chat_ids = self.get_channel_ids()
        results = []
        target_media_limit = max(500, limit)
        max_scan = 5000

        fully_fetched = True
        for chat_id in chat_ids:
            try:
                channel_count = 0
                media_count = 0
                if query_str:
                    async for msg in self.client.search_messages(chat_id=chat_id, query=query_str, limit=max_scan):
                        channel_count += 1
                        if self._has_media(msg):
                            results.append(msg)
                            media_count += 1
                            if media_count >= target_media_limit:
                                fully_fetched = False
                                break

                    # Fallback: if raw query_str returned 0 results, clean special characters/brackets and retry
                    if not results:
                        clean_q = re.sub(r'\[.*?\]|\(.*?\)', ' ', query_str)
                        clean_q = re.sub(r'\.(mkv|mp4|avi|zip|srt|vtt|ass)$', '', clean_q, flags=re.IGNORECASE)
                        clean_q = re.sub(r'[^a-zA-Z0-9\s]', ' ', clean_q)
                        clean_q = re.sub(r'\s+', ' ', clean_q).strip()

                        fallback_queries = []
                        if clean_q and clean_q != query_str:
                            fallback_queries.append(clean_q)

                        # Extract main title and episode number if present
                        ep_match = re.search(r'([A-Za-z0-9\s]+?)\s*(?:20[0-9]|1[0-9]{2}|\d{2,3})', clean_q)
                        if ep_match:
                            sub_q = ep_match.group(0).strip()
                            if sub_q not in fallback_queries:
                                fallback_queries.append(sub_q)

                        for f_q in fallback_queries:
                            logger.info(f"Retrying Telegram search with query '{f_q}'...")
                            async for msg in self.client.search_messages(chat_id=chat_id, query=f_q, limit=max_scan):
                                channel_count += 1
                                if self._has_media(msg):
                                    results.append(msg)
                                    media_count += 1
                                    if media_count >= target_media_limit:
                                        fully_fetched = False
                                        break
                            if results:
                                break
                else:
                    async for msg in self.client.get_chat_history(chat_id=chat_id, limit=max_scan):
                        channel_count += 1
                        if self._has_media(msg):
                            results.append(msg)
                            media_count += 1
                            if media_count >= target_media_limit:
                                fully_fetched = False
                                break

                if channel_count >= max_scan:
                    fully_fetched = False
            except Exception as e:
                logger.warning(f"Telegram query failed for {chat_id}: {e}")
                fully_fetched = False

        results.sort(key=lambda m: m.date, reverse=True)

        # Resolve all split parts for detected split files to prevent missing segments
        split_bases = set()
        for msg in results:
            media = msg.video or msg.document or msg.audio
            if media:
                fn = getattr(media, "file_name", "") or msg.caption or ""
                base, part = parse_split_info(fn)
                if base:
                    # Generate a clean, truncated search query for the split base
                    search_query = re.sub(r'[^a-zA-Z0-9\s]', ' ', base)
                    search_query = re.sub(r'\s+', ' ', search_query).strip()
                    words = search_query.split()
                    if words and words[-1].lower() in ('mkv', 'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'ts', 'm4v', 'zip'):
                        words = words[:-1]
                    if len(words) > 5:
                        search_query = " ".join(words[:5])
                    else:
                        search_query = " ".join(words)
                    for chat_id in chat_ids:
                        split_bases.add((chat_id, search_query))

        additional_messages = []
        for chat_id, base in split_bases:
            try:
                logger.info(f"Fetching all split parts matching base: {base}")
                async for msg in self.client.search_messages(chat_id=chat_id, query=base, limit=100):
                    if self._has_media(msg):
                        additional_messages.append(msg)
            except Exception as e:
                logger.warning(f"Failed to fetch additional split parts for {base}: {e}")

        # Merge and deduplicate by message ID
        deduped = {msg.id: msg for msg in results}
        for msg in additional_messages:
            deduped[msg.id] = msg

        final_results = list(deduped.values())
        final_results.sort(key=lambda m: m.date, reverse=True)

        self._search_cache[cache_key] = (now, final_results, fully_fetched)
        return final_results[:limit]

    async def get_message(self, message_id: int, chat_id: int = None) -> Message:
        if not self.is_running:
            await self.start()

        target_chat = chat_id if chat_id is not None else self.get_channel_ids()[0]

        cache_key = f"{target_chat}:{message_id}"
        now = time.time()
        if cache_key in self._message_cache:
            cached_time, cached_msg = self._message_cache[cache_key]
            if now - cached_time < Config.CACHE_TTL:
                return cached_msg

        try:
            msg = await self.client.get_messages(chat_id=target_chat, message_ids=message_id)
            self._message_cache[cache_key] = (now, msg)
            return msg
        except Exception as e:
            logger.error(f"Failed to fetch message {message_id} in channel {target_chat}: {e}")
            raise e

    def _has_media(self, msg: Message) -> bool:
        return bool(msg.video or msg.document or msg.audio)

tg_client_manager = TelegramClientManager()
