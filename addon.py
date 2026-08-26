import os
import sys
import time
import logging
import asyncio
from typing import Optional, List, Dict, Any, Union, Tuple

# Fix Pyrogram event loop crash on Python 3.10+ / 3.12 / 3.14
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import urllib.parse
import markupsafe
import re
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends, Response
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

class SafeStreamingResponse(StreamingResponse):
    async def __call__(self, scope, receive, send) -> None:
        async def safe_send(message):
            try:
                await send(message)
            except BaseException:
                return
        try:
            await super().__call__(scope, receive, safe_send)
        except BaseException:
            return

from config import Config
from tg_client import tg_client_manager

# Cache to store direct Debrid stream URLs mapped by filename
DEBRID_STREAM_URL_CACHE = {}

from utils import (
    format_size,
    matches_episode,
    get_metadata_from_cinemeta,
    matches_subtitle,
    get_search_query_from_filename,
    parse_split_info,
    is_video_file,
    matches_title,
    matches_any_title
)
from zip_helper import (
    list_zip_files,
    TelegramSeekableReader,
    get_zip_entry_data_offset,
    zip_compressed_generator
)
import anyio
from debrid import get_debrid_provider
from torrent_search import search_torrents
import hashlib
from subtitles_service import subtitle_generator


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] (%(name)s) - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("stremio_addon")

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        print("\n" + "=" * 60)
        print("   TELEGRAM ADDON BY SUNILROY-DEV")
        print("   GitHub: https://github.com/SunilRoy-dev/stremio-telegram-debrid")
        print("   For educational and personal testing only.")
        print("=" * 60 + "\n")
        
        tg_ready = Config.validate()
        if tg_ready:
            try:
                await tg_client_manager.start()
            except Exception as e:
                logger.warning(f"Telegram client manager failed to start: {e}")
        else:
            logger.info("ℹ️ Telegram credentials not fully configured or disabled - Telegram Media Vault offline (Web Cinema Hub online)")
        
        from dashboard_router import get_lan_ip
        lan_ip = get_lan_ip()
        print("=" * 60)
        print("   STREMIO MULTI-SOURCE CINEMA HUB READY")
        if getattr(Config, "ADDON_URL", None) and not Config.ADDON_URL.startswith("http://localhost"):
            print(f"   🌐 Public Domain:   {Config.ADDON_URL}/manifest.json")
            print(f"   🎛️ Domain Hub:      {Config.ADDON_URL}")
        print(f"   📱 LAN Network:     http://{lan_ip}:{Config.PORT}/manifest.json")
        print(f"   💻 Localhost:       http://127.0.0.1:{Config.PORT}/manifest.json")
        print("=" * 60 + "\n")
        yield
    finally:
        try:
            await tg_client_manager.stop()
        except Exception:
            pass

from nguonc_router import nguonc_router
from vsmov_router import vsmov_router
from kkphim_router import kkphim_router
from ridomovies_router import ridomovies_router
from clbphimxua_router import clbphimxua_router
from yanhh3d_router import yanhh3d_router
from topxx_router import topxx_router
from hhpanda_router import hhpanda_router
from moviesdrive_router import moviesdrive_router
from hdhub4u_router import hdhub4u_router
from uhdmovies_router import uhdmovies_router
from fourkhdhub_router import fourkhdhub_router
from hdtoday_router import hdtoday_router
from vidking_router import vidking_router
from ernax_router import ernax_router
from film4k_router import film4k_router
from iptv_router import iptv_router
from tvrun_router import tvrun_router
from movies2watch_router import movies2watch_router
from dashboard_router import dashboard_router

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_router)
app.include_router(nguonc_router, prefix="/nguonc", tags=["NguonC Cinema"])
app.include_router(vsmov_router, prefix="/vsmov", tags=["VSMov Cinema"])
app.include_router(kkphim_router, prefix="/kkphim", tags=["KKPhim Cinema"])
app.include_router(ridomovies_router, prefix="/ridomovies", tags=["RidoMovies Cinema"])
app.include_router(clbphimxua_router, prefix="/clbphimxua", tags=["CLBPhimXua Cinema"])
app.include_router(yanhh3d_router, prefix="/yanhh3d", tags=["Yanhh3d Anime 3D"])
app.include_router(topxx_router, prefix="/topxx", tags=["TopXX Cinema"])
app.include_router(hhpanda_router, prefix="/hhpanda", tags=["HHPanda Anime 3D"])
app.include_router(moviesdrive_router, prefix="/moviesdrive", tags=["MoviesDrive Cinema"])
app.include_router(hdhub4u_router, prefix="/hdhub4u", tags=["HDHub4u Cinema"])
app.include_router(uhdmovies_router, prefix="/uhdmovies", tags=["UHDMovies 4K Cinema"])
app.include_router(fourkhdhub_router, prefix="/4khdhub", tags=["4KHDHub 4K Cinema"])
app.include_router(hdtoday_router, prefix="/hdtoday", tags=["HDToday Cinema"])
app.include_router(movies2watch_router, prefix="/movies2watch", tags=["Movies2Watch Cinema"])
app.include_router(vidking_router, prefix="/vidking", tags=["Vidking Player"])
app.include_router(ernax_router, prefix="/ernax", tags=["Ernax Player"])
app.include_router(film4k_router, prefix="/film4k", tags=["Film4k Live TV"])
app.include_router(iptv_router, prefix="/iptv", tags=["IPTV Org Live TV by Country"])
app.include_router(tvrun_router, prefix="/tvrun", tags=["TVRun Free Global Live TV"])


@app.get("/tv", include_in_schema=False)
@app.get("/player", include_in_schema=False)
async def tv_redirect():
    return RedirectResponse(url="/film4k/tv", status_code=302)


@app.get("/iptv-tv", include_in_schema=False)
@app.get("/iptv-player", include_in_schema=False)
async def iptv_redirect():
    return RedirectResponse(url="/iptv/tv", status_code=302)


@app.get("/tvrun-tv", include_in_schema=False)
@app.get("/tvrun-player", include_in_schema=False)
async def tvrun_redirect():
    return RedirectResponse(url="/tvrun/tv", status_code=302)





def group_tg_messages(messages: list) -> list:
    grouped = {}
    standalone = []
    
    for msg in messages:
        media = msg.video or msg.document or msg.audio
        if not media:
            continue
            
        fn = getattr(media, "file_name", "") or msg.caption or f"Telegram File {msg.id}"
        base, part = parse_split_info(fn)
        
        if base and part is not None:
            key = base.lower()
            if key not in grouped:
                grouped[key] = {
                    "base_name": base,
                    "parts": {}
                }
            grouped[key]["parts"][part] = msg
        else:
            standalone.append(msg)
            
    results = []
    for key, data in grouped.items():
        parts = data["parts"]
        base_name = data["base_name"]
        
        if len(parts) == 1:
            results.append(list(parts.values())[0])
        else:
            sorted_parts = [msg for part, msg in sorted(parts.items())]
            results.append((base_name, sorted_parts))
            
    for msg in standalone:
        results.append(msg)
        
    return results

def verify_api_key(request: Request):
    if Config.API_KEY:
        api_key = request.query_params.get("api_key", "") or request.path_params.get("api_key", "")
        if api_key != Config.API_KEY:
            raise HTTPException(status_code=403, detail="Unauthorized: Invalid API Key")

def get_manifest(api_key: str = ""):
    query_suffix = f"?api_key={api_key}" if api_key else ""
    show_on_board = getattr(Config, "ENABLE_BOARD_TELEGRAM", True)
    main_req = not show_on_board

    resources = ["meta", "stream"]
    if getattr(Config, "ENABLE_SUBTITLES", True):
        resources.append("subtitles")

    return {
        "id": "community.telegram.stremio.addon",
        "version": "1.0.0",
        "name": "Telegram Addon by SunilRoy-dev",
        "description": "Personal Telegram streaming proxy. For educational & personal testing only. Do not use for unauthorized hosting of copyrighted media.",
        "logo": "https://upload.wikimedia.org/wikipedia/commons/8/82/Telegram_logo.svg",
        "resources": resources,
        "types": ["movie", "series", "anime", "other"],
        "catalogs": [
            {
                "type": "movie",
                "id": "telegram_movies",
                "name": "Telegram Movies",
                "extra": [
                    {"name": "genre", "options": ["Tất cả"], "isRequired": main_req},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False}
                ]
            },
            {
                "type": "series",
                "id": "telegram_series",
                "name": "Telegram Series",
                "extra": [
                    {"name": "genre", "options": ["Tất cả"], "isRequired": main_req},
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False}
                ]
            }
        ],
        "behaviorHints": {
            "configurable": False,
            "configurationRequired": False
        }
    }

@app.api_route("/", methods=["GET", "HEAD"])
async def landing(request: Request):
    redirect_url = "/dashboard"
    if request.url.query:
        redirect_url = f"/dashboard?{request.url.query}"
    return RedirectResponse(url=redirect_url, status_code=302)

@app.api_route("/manifest.json", methods=["GET", "HEAD"])
@app.api_route("/{api_key}/manifest.json", methods=["GET", "HEAD"])
async def manifest_endpoint(api_key: str = ""):
    if Config.API_KEY and api_key != Config.API_KEY:
        return JSONResponse({"detail": "Unauthorized: Invalid API Key"}, status_code=403)
    return get_manifest(api_key)

@app.api_route("/subtitles/manifest.json", methods=["GET", "HEAD"])
@app.api_route("/{api_key}/subtitles/manifest.json", methods=["GET", "HEAD"])
async def subtitles_manifest_endpoint(api_key: str = ""):
    if Config.API_KEY and api_key != Config.API_KEY:
        return JSONResponse({"detail": "Unauthorized: Invalid API Key"}, status_code=403)
    if not getattr(Config, "ENABLE_SUBTITLES", True):
        return JSONResponse({
            "id": "community.vietsub.stremio.subtitles",
            "version": "1.0.0",
            "name": "AI VietSub & OpenSubtitles Engine (Disabled)",
            "description": "Tính năng phụ đề hiện đang bị tắt trong Dashboard.",
            "resources": [],
            "types": []
        })
    return {
        "id": "community.vietsub.stremio.subtitles",
        "version": "1.0.0",
        "name": "AI VietSub & OpenSubtitles Engine",
        "description": "Kho phụ đề đa ngôn ngữ OpenSubtitles và Tự động dịch phụ đề tiếng Việt (VietSub) chuẩn AI siêu tốc cho mọi phim & series.",
        "logo": "https://cdn-icons-png.flaticon.com/512/3845/3845868.png",
        "resources": [
            {
                "name": "subtitles",
                "types": ["movie", "series", "anime", "other"],
                "idPrefixes": ["tt", "kitsu:", "moviesdrive:", "vidking:", "hdtoday:"]
            }
        ],
        "types": ["movie", "series", "anime", "other"],
        "catalogs": []
    }

@app.get("/catalog/{type}/{catalog_id}.json", dependencies=[Depends(verify_api_key)])
@app.get("/catalog/{type}/{catalog_id}/{extra}.json", dependencies=[Depends(verify_api_key)])
@app.get("/{api_key}/catalog/{type}/{catalog_id}.json", dependencies=[Depends(verify_api_key)])
@app.get("/{api_key}/catalog/{type}/{catalog_id}/{extra}.json", dependencies=[Depends(verify_api_key)])
async def catalog_handler(
    request: Request,
    type: str, 
    catalog_id: str, 
    extra: str = None,
    api_key: str = ""
):
    if catalog_id.startswith("moviesdrive_") or catalog_id.startswith("moviesdrive:"):
        from moviesdrive_router import catalog_extra_endpoint, catalog_endpoint
        if extra:
            return await catalog_extra_endpoint(request, type, catalog_id, extra)
        return await catalog_endpoint(request, type, catalog_id)

    if catalog_id.startswith("hdhub4u_") or catalog_id.startswith("hdhub4u:"):
        from hdhub4u_router import catalog_extra_endpoint as hdh_cat_extra, catalog_endpoint as hdh_cat
        if extra:
            return await hdh_cat_extra(type, catalog_id, extra)
        return await hdh_cat(type, catalog_id)

    if type not in ["movie", "series"]:
        return {"metas": []}
        
    query = ""
    skip = 0
    if extra:
        params = urllib.parse.parse_qs(extra)
        if "search" in params:
            query = params["search"][0]
        if "skip" in params:
            try:
                skip = int(params["skip"][0])
            except ValueError:
                pass

    try:
        messages = await tg_client_manager.search_messages(query=query, limit=skip + 100)
    except Exception as e:
        logger.error(f"Catalog search failed: {e}")
        return {"metas": []}

    grouped_items = group_tg_messages(messages)
    metas = []
    logo_url = f"{Config.ADDON_URL}/stremio_telegram_logo.png" if getattr(Config, "ADDON_URL", None) else None
    
    for item in grouped_items:
        if isinstance(item, tuple):
            base_name, parts = item
            total_size = sum((x.video or x.document or x.audio).file_size for x in parts if (x.video or x.document or x.audio))
            first_msg = parts[0]
            chat_id = first_msg.chat.id
            msg_ids = ",".join(str(x.id) for x in parts)
            
            is_zip = False
            if base_name.lower().endswith(".zip"):
                try:
                    entries = await list_zip_files(tg_client_manager.client, parts)
                    video_entries = [e for e in entries if is_video_file(e.filename)]
                    if video_entries:
                        is_zip = True
                        for entry in video_entries:
                            tg_id = f"tgfile_splitzip_{chat_id}_{msg_ids}//{entry.filename}"
                            metas.append({
                                "id": tg_id,
                                "type": type,
                                "name": entry.filename,
                                "description": f"💾 Telegram ZIP Entry\n📦 Size: {format_size(entry.file_size)}\n📂 ZIP Archive: {base_name}",
                                "poster": get_message_thumbnail_url(first_msg, logo_url),
                            })
                except Exception as e:
                    logger.error(f"Error reading split ZIP archive: {e}")
                    
            if not is_zip:
                tg_id = f"tgfile_split_{chat_id}_{msg_ids}"
                metas.append({
                    "id": tg_id,
                    "type": type,
                    "name": base_name,
                    "description": f"💾 Telegram File (Split Parts: {len(parts)})\n📦 Total Size: {format_size(total_size)}",
                    "poster": get_message_thumbnail_url(first_msg, logo_url),
                })
        else:
            msg = item
            media = msg.video or msg.document or msg.audio
            file_name = getattr(media, "file_name", None) or msg.caption or f"Telegram File {msg.id}"
            file_size = media.file_size
            caption = msg.caption or ""
            
            is_zip = False
            if file_name.lower().endswith(".zip"):
                try:
                    entries = await list_zip_files(tg_client_manager.client, msg)
                    video_entries = [e for e in entries if is_video_file(e.filename)]
                    if video_entries:
                        is_zip = True
                        for entry in video_entries:
                            tg_id = f"tgfile_zip_{msg.chat.id}_{msg.id}//{entry.filename}"
                            metas.append({
                                "id": tg_id,
                                "type": type,
                                "name": entry.filename,
                                "description": f"💾 Telegram ZIP Entry\n📦 Size: {format_size(entry.file_size)}\n📂 ZIP Archive: {file_name}",
                                "poster": get_message_thumbnail_url(msg, logo_url),
                            })
                except Exception as e:
                    logger.error(f"Error reading standalone ZIP archive: {e}")
                    
            if not is_zip:
                tg_id = f"tgfile_{msg.chat.id}_{msg.id}"
                metas.append({
                    "id": tg_id,
                    "type": type,
                    "name": file_name,
                    "description": f"💾 Telegram File\n📦 Size: {format_size(file_size)}\n💬 {caption}" if caption else f"💾 Telegram File\n📦 Size: {format_size(file_size)}",
                    "poster": get_message_thumbnail_url(msg, logo_url),
                })
            
    return {"metas": metas[skip:skip+100]}

from fastapi.responses import FileResponse
import os

@app.get("/stremio_telegram_logo.png")
async def get_logo():
    if os.path.exists("stremio_telegram_logo.png"):
        return FileResponse("stremio_telegram_logo.png")
    return Response(status_code=404)

@app.get("/stremio_telegram_banner.png")
async def get_banner():
    if os.path.exists("stremio_telegram_banner.png"):
        return FileResponse("stremio_telegram_banner.png")
    return Response(status_code=404)

@app.get("/meta/{type}/{meta_id}.json", dependencies=[Depends(verify_api_key)])
@app.get("/{api_key}/meta/{type}/{meta_id}.json", dependencies=[Depends(verify_api_key)])
async def meta_handler(type: str, meta_id: str, api_key: str = ""):
    if meta_id.startswith("moviesdrive:"):
        from moviesdrive_router import meta_endpoint as md_meta
        return await md_meta(type, meta_id)
    if meta_id.startswith("hdhub4u:"):
        from hdhub4u_router import meta_endpoint as hdh_meta
        return await hdh_meta(type, meta_id)
    if not meta_id.startswith("tgfile_"):
        return {"meta": {}}
        
    try:
        is_zip_entry = False
        zip_entry_filename = ""
        base_meta_id = meta_id
        if "//" in meta_id:
            is_zip_entry = True
            base_meta_id, zip_entry_filename = meta_id.split("//", 1)
            
        chat_id_val = None
        msg_ids_str = ""
        is_split = False
        
        if base_meta_id.startswith("tgfile_splitzip_"):
            is_split = True
            parts = base_meta_id.split("_")
            chat_id = parts[2]
            msg_ids_str = parts[3]
        elif base_meta_id.startswith("tgfile_split_"):
            is_split = True
            parts = base_meta_id.split("_")
            chat_id = parts[2]
            msg_ids_str = parts[3]
        elif base_meta_id.startswith("tgfile_zip_"):
            parts = base_meta_id.split("_")
            chat_id = parts[2]
            msg_ids_str = parts[3]
        else:
            parts = base_meta_id.split("_")
            chat_id = parts[1]
            msg_ids_str = parts[2]
            
        try:
            chat_id_val = int(chat_id)
        except ValueError:
            chat_id_val = chat_id
            
        msg_id_list = [int(x) for x in msg_ids_str.split(",") if x.strip().isdigit()]
        
        messages = []
        for msg_id in msg_id_list:
            msg = await tg_client_manager.get_message(msg_id, chat_id=chat_id_val)
            if msg:
                messages.append(msg)
                
        if not messages:
            return {"meta": {}}
            
        first_msg = messages[0]
        media = first_msg.video or first_msg.document or first_msg.audio
        first_fn = getattr(media, "file_name", "video.mp4") or "video.mp4"
        
        if is_zip_entry and zip_entry_filename:
            file_name = zip_entry_filename
            zip_entries = await list_zip_files(tg_client_manager.client, messages)
            file_size = 0
            for entry in zip_entries:
                if entry.filename == zip_entry_filename:
                    file_size = entry.file_size
                    break
            description = f"💾 Telegram ZIP Entry\n📦 Size: {format_size(file_size)}\n📂 ZIP Archive: {first_fn}"
        else:
            file_name = first_fn
            if is_split:
                base_name, _ = parse_split_info(first_fn)
                file_name = base_name or first_fn
                total_size = sum((x.video or x.document or x.audio).file_size for x in messages if (x.video or x.document or x.audio))
                description = f"💾 Telegram File (Split Parts: {len(messages)})\n📦 Total Size: {format_size(total_size)}"
            else:
                total_size = media.file_size
                caption = first_msg.caption or ""
                description = f"💾 Telegram File\n📦 Size: {format_size(total_size)}\n💬 {caption}" if caption else f"💾 Telegram File\n📦 Size: {format_size(total_size)}"
                
        logo_url = f"{Config.ADDON_URL}/stremio_telegram_logo.png" if getattr(Config, "ADDON_URL", None) else None
        poster_url = get_message_thumbnail_url(first_msg, logo_url)
        meta = {
            "id": meta_id,
            "type": type,
            "name": file_name,
            "description": description,
            "poster": poster_url,
            "posterShape": "poster",
            "background": poster_url,
        }
        
        if type == "series":
            meta["videos"] = [
                {
                    "id": meta_id,
                    "title": file_name,
                    "season": 1,
                    "episode": 1,
                    "thumbnail": poster_url,
                }
            ]
            
        return {"meta": meta}
    except Exception as e:
        logger.error(f"Failed to generate metadata for {meta_id}: {e}")
        return {"meta": {}}


async def fetch_opensubtitles(imdb_id: str, media_type: str = "movie") -> list:
    import httpx
    url = f"https://opensubtitles-v3.strem.io/subtitles/{media_type}/{urllib.parse.quote(imdb_id)}.json"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.json().get("subtitles", [])
    except Exception as e:
        logger.error(f"Failed to fetch subtitles from OpenSubtitles for {imdb_id}: {e}")
    return []

async def prepare_existing_vi_sub_and_tts(cache_key: str, sub_url: str):
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(sub_url)
            if resp.status_code == 200:
                content = resp.text
                from subtitles_service import CACHE_DIR as SUB_CACHE_DIR
                sub_path = os.path.join(SUB_CACHE_DIR, f"{cache_key}.srt")
                with open(sub_path, "w", encoding="utf-8") as f:
                    f.write(content)
                from tts_service import tts_manager
                await tts_manager.start_tts_generation(cache_key, content)
            else:
                logger.error(f"Failed to download existing VI subtitle from {sub_url}: status {resp.status_code}")
    except Exception as e:
        logger.error(f"Failed to prepare existing VI subtitle for TTS: {e}")

async def find_subtitles_for_video(
    video_filename: str,
    api_key: str = "",
    cached_messages=None,
    video_url: str = None,
    imdb_id: str = None,
    media_type: str = "movie"
) -> list:
    if not getattr(Config, "ENABLE_SUBTITLES", True):
        return []
    subtitles = []
    search_results = cached_messages or []
    query_param = f"?api_key={api_key}" if api_key else ""
    
    # 1. Search OpenSubtitles if imdb_id is provided
    if imdb_id:
        try:
            os_subs = await fetch_opensubtitles(imdb_id, media_type)
            for sub in os_subs:
                lang = sub.get("lang")
                if lang in ("vie", "vi", "eng"):
                    sub_id_hash = hashlib.md5(sub["url"].encode()).hexdigest()
                    subtitles.append({
                        "id": f"os_{lang}_{sub_id_hash}",
                        "url": sub["url"],
                        "lang": "vie" if lang in ("vie", "vi") else "eng"
                    })
        except Exception as e:
            logger.error(f"Failed to process OpenSubtitles tracks: {e}")
            
    if not search_results:
        query = get_search_query_from_filename(video_filename)
        if query:
            try:
                search_results = await tg_client_manager.search_messages(query=query, limit=20)
            except Exception as e:
                logger.error(f"Subtitle search failed for '{query}': {e}")
                
    seen_msg_ids = set()
    for msg in search_results:
        if msg.id in seen_msg_ids:
            continue
            
        doc = msg.document or msg.audio or msg.video
        if not doc:
            continue
            
        sub_fn = getattr(doc, "file_name", "") or ""
        if sub_fn.lower().endswith(('.srt', '.vtt', '.ass')):
            if matches_subtitle(video_filename, sub_fn):
                seen_msg_ids.add(msg.id)
                
                lang = "eng"
                sub_fn_lower = sub_fn.lower()
                if ".spa" in sub_fn_lower or "spanish" in sub_fn_lower:
                    lang = "spa"
                elif ".fre" in sub_fn_lower or "french" in sub_fn_lower:
                    lang = "fre"
                
                subtitles.append({
                    "id": f"tgsub_{msg.chat.id}_{msg.id}",
                    "url": f"{Config.ADDON_URL}/stream/subtitle/{msg.chat.id}/{msg.id}/{urllib.parse.quote(sub_fn)}{query_param}",
                    "lang": lang
                })
                
    if Config.AUTO_VIET_SUB:
        has_vi = any(sub.get("lang") in ("vie", "vi") for sub in subtitles)
        cache_key = hashlib.md5(video_filename.encode("utf-8")).hexdigest()
        if video_url:
            subtitle_generator.register_video_url(cache_key, video_url)
        
        if has_vi:
            vi_sub = next(sub for sub in subtitles if sub.get("lang") in ("vie", "vi"))
            asyncio.create_task(prepare_existing_vi_sub_and_tts(cache_key, vi_sub["url"]))
        else:
            source_sub = None
            for s in subtitles:
                if s["lang"] == "eng":
                    source_sub = s
                    break
            if not source_sub and subtitles:
                source_sub = subtitles[0]
                
            source_url = source_sub["url"] if source_sub else None
            
            params = {}
            if api_key:
                params["api_key"] = api_key
            if source_url:
                params["source_url"] = source_url
            if video_url:
                params["video_url"] = video_url
            params["filename"] = video_filename
            
            target_id = imdb_id or cache_key
            sub_url = f"{Config.ADDON_URL}/subtitles/vtt/{urllib.parse.quote(target_id)}.vtt?type={media_type}"
            if api_key:
                sub_url = f"{Config.ADDON_URL}/{api_key}/subtitles/vtt/{urllib.parse.quote(target_id)}.vtt?type={media_type}"
            
            subtitles.append({
                "id": f"vi_synced_{cache_key}",
                "url": sub_url,
                "lang": "vie",
                "name": "🇻🇳 Tiếng Việt Đồng Bộ Chuẩn 100% (AI Instant)"
            })
            
            # Preload in background
            try:
                from subtitles_service import get_or_generate_synced_vtt, STREAM_VIDEO_URL_CACHE
                if video_url:
                    STREAM_VIDEO_URL_CACHE[target_id] = video_url
                asyncio.create_task(get_or_generate_synced_vtt(media_type, target_id, video_url=video_url))
            except Exception:
                pass
            
    return subtitles

@app.get("/subtitles/{type}/{id}.json")
@app.get("/subtitles/{type}/{id}/{extra:path}")
@app.get("/{api_key}/subtitles/{type}/{id}.json")
@app.get("/{api_key}/subtitles/{type}/{id}/{extra:path}")
async def root_subtitles_handler(request: Request, type: str, id: str, extra: str = "", api_key: str = ""):
    if not getattr(Config, "ENABLE_SUBTITLES", True):
        return JSONResponse(content={"subtitles": []})
    if id.startswith("4khdhub:"):
        from fourkhdhub_router import subtitles_endpoint as fourkhd_subtitles
        return await fourkhd_subtitles(request, type, id, extra)
    if id.startswith("uhdmovies:"):
        from uhdmovies_router import uhdmovies_subtitles
        return await uhdmovies_subtitles(request, type, id, extra)
    from moviesdrive_router import moviesdrive_subtitles
    return await moviesdrive_subtitles(request, type, id, extra)

@app.api_route("/subtitles/vtt/{item_id}.vtt", methods=["GET", "HEAD"])
@app.api_route("/{api_key}/subtitles/vtt/{item_id}.vtt", methods=["GET", "HEAD"])
async def root_serve_synced_vtt(request: Request, item_id: str, type: str = "movie"):
    from moviesdrive_router import serve_synced_vtt
    return await serve_synced_vtt(request, item_id, type)

@app.api_route("/subtitles/srt/{item_id}.srt", methods=["GET", "HEAD"])
@app.api_route("/subtitles/srt/{item_id}", methods=["GET", "HEAD"])
@app.api_route("/{api_key}/subtitles/srt/{item_id}.srt", methods=["GET", "HEAD"])
@app.api_route("/{api_key}/subtitles/srt/{item_id}", methods=["GET", "HEAD"])
async def root_serve_synced_srt(request: Request, item_id: str, type: str = "movie"):
    from moviesdrive_router import serve_synced_srt
    return await serve_synced_srt(request, item_id, type)

@app.get("/stream/{type}/{stream_id}.json")
@app.get("/{api_key}/stream/{type}/{stream_id}.json")
async def stream_handler(
    type: str, 
    stream_id: str,
    request: Request,
    api_key: str = ""
):
    if Config.API_KEY:
        actual_key = api_key or request.query_params.get("api_key", "")
        if actual_key != Config.API_KEY:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
    streams = []
    query_param = f"?api_key={api_key}" if api_key else ""

    if stream_id.startswith("moviesdrive:"):
        from moviesdrive_router import stream_endpoint as md_stream
        return await md_stream(request, type, stream_id)

    if stream_id.startswith("hdhub4u:"):
        from hdhub4u_router import stream_endpoint as hdh_stream
        return await hdh_stream(request, type, stream_id)

    if stream_id.startswith("uhdmovies:"):
        from uhdmovies_router import stream_endpoint as uhd_stream
        return await uhd_stream(request, type, stream_id)

    if stream_id.startswith("4khdhub:"):
        from fourkhdhub_router import stream_endpoint as fourkhd_stream
        return await fourkhd_stream(request, type, stream_id)

    if stream_id.startswith("tgfile_"):
        if "//" in stream_id:
            base_stream_id, zip_entry_filename = stream_id.split("//", 1)
            is_split = False
            if base_stream_id.startswith("tgfile_splitzip_"):
                is_split = True
                parts = base_stream_id.split("_")
                chat_id = parts[2]
                msg_ids = parts[3]
            elif base_stream_id.startswith("tgfile_split_"):
                is_split = True
                parts = base_stream_id.split("_")
                chat_id = parts[2]
                msg_ids = parts[3]
            elif base_stream_id.startswith("tgfile_zip_"):
                parts = base_stream_id.split("_")
                chat_id = parts[2]
                msg_ids = parts[3]
            else:
                parts = base_stream_id.split("_")
                chat_id = parts[1]
                msg_ids = parts[2]
                
            try:
                chat_id_val = int(chat_id)
            except ValueError:
                chat_id_val = chat_id
                
            msg_id_list = [int(x) for x in msg_ids.split(",") if x.strip().isdigit()]
            
            try:
                messages = []
                for msg_id in msg_id_list:
                    msg = await tg_client_manager.get_message(msg_id, chat_id=chat_id_val)
                    if msg:
                        messages.append(msg)
                        
                if messages:
                    zip_entries = await list_zip_files(tg_client_manager.client, messages)
                    file_size = 0
                    for entry in zip_entries:
                        if entry.filename == zip_entry_filename:
                            file_size = entry.file_size
                            break
                            
                    stream_url = f"{Config.ADDON_URL}/stream/zip/{chat_id}/{msg_ids}/{urllib.parse.quote(zip_entry_filename)}{query_param}"
                    subtitles = await find_subtitles_for_video(zip_entry_filename, api_key=api_key, video_url=stream_url)
                    
                    streams.append({
                        "name": "▶ TG ZIP Play",
                        "title": f"{zip_entry_filename}\n💾 Stream ZIP entry | 📦 {format_size(file_size)}",
                        "url": stream_url,
                        "subtitles": subtitles,
                        "behaviorHints": {
                            "notWebReady": True,
                        }
                    })
            except Exception as e:
                logger.error(f"Failed resolving zip stream for {stream_id}: {e}")
        elif stream_id.startswith("tgfile_split_"):
            parts = stream_id.split("_")
            if len(parts) >= 4:
                chat_id = parts[2]
                msg_ids = parts[3]
                try:
                    msg_id_list = [int(x) for x in msg_ids.split(",") if x.isdigit()]
                    try:
                        chat_id_val = int(chat_id)
                    except ValueError:
                        chat_id_val = chat_id
                    
                    first_msg = await tg_client_manager.get_message(msg_id_list[0], chat_id=chat_id_val)
                    media = first_msg.video or first_msg.document or first_msg.audio
                    first_fn = getattr(media, "file_name", "video.mp4") or "video.mp4"
                    base_name, _ = parse_split_info(first_fn)
                    if not base_name:
                        base_name = first_fn
                        
                    total_size = 0
                    for m_id in msg_id_list:
                        m = await tg_client_manager.get_message(m_id, chat_id=chat_id_val)
                        if m:
                            med = m.video or m.document or m.audio
                            if med:
                                total_size += med.file_size
                                
                    stream_url = f"{Config.ADDON_URL}/stream/split/{chat_id}/{msg_ids}/{urllib.parse.quote(base_name)}{query_param}"
                    
                    streams.append({
                        "name": "▶ TG Play (Split)",
                        "title": f"{base_name}\n💾 Stitch stream | 📦 {format_size(total_size)}",
                        "url": stream_url,
                        "behaviorHints": {
                            "notWebReady": True,
                        }
                    })
                except Exception as e:
                    logger.error(f"Failed resolving split stream for {stream_id}: {e}")
        else:
            parts = stream_id.split("_")
            if len(parts) >= 3:
                chat_id = parts[1]
                msg_id = parts[2]
                try:
                    try:
                        chat_id_val = int(chat_id)
                    except ValueError:
                        chat_id_val = chat_id
                    msg = await tg_client_manager.get_message(int(msg_id), chat_id=chat_id_val)
                    media = msg.video or msg.document or msg.audio
                    file_name = getattr(media, "file_name", "video.mp4") or "video.mp4"
                    file_size = media.file_size
                    
                    stream_url = f"{Config.ADDON_URL}/stream/file/{chat_id}/{msg_id}/{urllib.parse.quote(file_name)}{query_param}"
                    subtitles = await find_subtitles_for_video(file_name, api_key=api_key, video_url=stream_url)
                    
                    streams.append({
                        "name": "▶ TG Play",
                        "title": f"{file_name}\n💾 Direct stream | 📦 {format_size(file_size)}",
                        "url": stream_url,
                        "subtitles": subtitles,
                        "behaviorHints": {
                            "notWebReady": True,
                        }
                    })
                except Exception as e:
                    logger.error(f"Failed resolving direct stream for {stream_id}: {e}")

    elif stream_id.startswith("tt"):
        imdb_id = stream_id
        season = None
        episode = None
        
        if ":" in stream_id:
            parts = stream_id.split(":")
            imdb_id = parts[0]
            season = int(parts[1])
            episode = int(parts[2])
            
        try:
            meta = await get_metadata_from_cinemeta(type, imdb_id)
            movie_name = meta.get("name")
            
            if movie_name:
                target_titles = [movie_name]
                if meta.get("aka"):
                    target_titles.extend(meta["aka"])
                    
                seen_titles = set()
                unique_titles = []
                for t_title in target_titles:
                    t_clean = t_title.strip().lower()
                    if t_clean and t_clean not in seen_titles:
                        seen_titles.add(t_clean)
                        unique_titles.append(t_title)
                
                tg_results = []
                seen_msg_ids = set()
                for query in unique_titles[:3]:
                    logger.info(f"Searching Telegram for query: '{query}'")
                    try:
                        res = await tg_client_manager.search_messages(query=query, limit=40)
                        for msg in res:
                            if msg.id not in seen_msg_ids:
                                seen_msg_ids.add(msg.id)
                                tg_results.append(msg)
                    except Exception as e:
                        logger.error(f"Telegram search for query '{query}' failed: {e}")
                
                logger.info(f"Telegram search returned {len(tg_results)} unique results for titles: {unique_titles[:3]}")
                grouped_results = group_tg_messages(tg_results)
                
                for item in grouped_results:
                    if isinstance(item, tuple):
                        base_name, parts = item
                        first_msg = parts[0]
                        media = first_msg.video or first_msg.document or first_msg.audio
                        file_name = getattr(media, "file_name", "") or ""
                        
                        if not matches_any_title(base_name, unique_titles):
                            continue
                            
                        if type == "series" and not matches_episode(file_name, season, episode):
                            continue
                            
                        total_size = sum((x.video or x.document or x.audio).file_size for x in parts if (x.video or x.document or x.audio))
                        msg_ids = ",".join(str(x.id) for x in parts)
                        chat_id = first_msg.chat.id
                        
                        is_zip = False
                        if base_name.lower().endswith(".zip"):
                            try:
                                entries = await list_zip_files(tg_client_manager.client, parts)
                                video_entries = [e for e in entries if is_video_file(e.filename)]
                                if video_entries:
                                    is_zip = True
                                    for entry in video_entries:
                                        if type == "series" and not matches_episode(entry.filename, season, episode):
                                            continue
                                        stream_url = f"{Config.ADDON_URL}/stream/zip/{chat_id}/{msg_ids}/{urllib.parse.quote(entry.filename)}{query_param}"
                                        subtitles = await find_subtitles_for_video(entry.filename, api_key=api_key, cached_messages=tg_results, video_url=stream_url, imdb_id=imdb_id, media_type=type)
                                        streams.append({
                                            "name": "▶ TG ZIP Play (Split)",
                                            "title": f"{entry.filename}\n💾 Stream ZIP entry | 📦 {format_size(entry.file_size)}",
                                            "url": stream_url,
                                            "subtitles": subtitles,
                                            "behaviorHints": {
                                                "notWebReady": True,
                                            }
                                        })
                            except Exception as e:
                                logger.error(f"Error checking split ZIP for IMDB: {e}")
                                
                        if not is_zip:
                            if not is_video_file(base_name):
                                continue
                            stream_url = f"{Config.ADDON_URL}/stream/split/{chat_id}/{msg_ids}/{urllib.parse.quote(base_name)}{query_param}"
                            streams.append({
                                "name": "▶ TG Play (Split)",
                                "title": f"{base_name}\n💾 Stitch stream | 📦 {format_size(total_size)}",
                                "url": stream_url,
                                "behaviorHints": {
                                    "notWebReady": True,
                                }
                            })
                    else:
                        msg = item
                        media = msg.video or msg.document or msg.audio
                        file_name = getattr(media, "file_name", None) or msg.caption or ""
                        
                        if not matches_any_title(file_name, unique_titles):
                            continue
                            
                        if type == "series" and not matches_episode(file_name, season, episode):
                            continue
                            
                        file_size = media.file_size
                        chat_id = msg.chat.id
                        
                        is_zip = False
                        if file_name.lower().endswith(".zip"):
                            try:
                                entries = await list_zip_files(tg_client_manager.client, msg)
                                video_entries = [e for e in entries if is_video_file(e.filename)]
                                if video_entries:
                                    is_zip = True
                                    for entry in video_entries:
                                        if type == "series" and not matches_episode(entry.filename, season, episode):
                                            continue
                                        stream_url = f"{Config.ADDON_URL}/stream/zip/{chat_id}/{msg.id}/{urllib.parse.quote(entry.filename)}{query_param}"
                                        subtitles = await find_subtitles_for_video(entry.filename, api_key=api_key, cached_messages=tg_results, video_url=stream_url, imdb_id=imdb_id, media_type=type)
                                        streams.append({
                                            "name": "▶ TG ZIP Play",
                                            "title": f"{entry.filename}\n💾 Stream ZIP entry | 📦 {format_size(entry.file_size)}",
                                            "url": stream_url,
                                            "subtitles": subtitles,
                                            "behaviorHints": {
                                                "notWebReady": True,
                                            }
                                        })
                            except Exception as e:
                                logger.error(f"Error checking standalone ZIP for IMDB: {e}")
                                
                        if not is_zip:
                            if not is_video_file(file_name):
                                continue
                            stream_url = f"{Config.ADDON_URL}/stream/file/{chat_id}/{msg.id}/{urllib.parse.quote(file_name)}{query_param}"
                            subtitles = await find_subtitles_for_video(file_name, api_key=api_key, cached_messages=tg_results, video_url=stream_url, imdb_id=imdb_id, media_type=type)
                            
                            streams.append({
                                "name": "▶ TG Play",
                                "title": f"{file_name}\n💾 Telegram File | 📦 {format_size(file_size)}",
                                "url": stream_url,
                                "subtitles": subtitles,
                                "behaviorHints": {
                                    "notWebReady": True,
                                }
                            })
                            
                # 2. Torrent & Debrid Search
                debrid_provider = get_debrid_provider()
                if debrid_provider:
                    search_query = movie_name
                    if type == "series" and season is not None and episode is not None:
                        search_query = f"{movie_name} S{season:02d}E{episode:02d}"
                        
                    logger.info(f"Searching torrents for: '{search_query}' (IMDb: {imdb_id})")
                    torrents = await search_torrents(search_query, imdb_id=imdb_id)
                    
                    if torrents:
                        hashes = []
                        for t in torrents:
                            h = _extract_hash_from_magnet(t["magnet"])
                            if h:
                                hashes.append(h)
                                
                        cache_status = {}
                        if hashes:
                            try:
                                cache_status = await debrid_provider.check_availability(hashes)
                            except Exception as e:
                                logger.error(f"Debrid cache check failed: {e}")
                                
                        for t in torrents:
                            if not matches_any_title(t["title"], unique_titles):
                                  continue
                            mag = t["magnet"]
                            h = _extract_hash_from_magnet(mag)
                            is_cached = cache_status.get(h.lower(), False) if h else False
                            
                            import base64
                            mag_b64 = base64.b64encode(mag.encode()).decode()
                            provider_name = "realdebrid" if Config.REAL_DEBRID_API_KEY else ("torbox" if Config.TORBOX_API_KEY else "qbittorrent")
                            stream_url = f"{Config.ADDON_URL}/stream/debrid/{provider_name}/{mag_b64}/{urllib.parse.quote(t['title'])}?imdb={stream_id}"
                            DEBRID_STREAM_URL_CACHE[t['title']] = (provider_name, mag)
                            if query_param:
                                q_p = query_param.replace("?", "&")
                                stream_url += q_p
                                
                            size_str = format_size(t["size"])
                            if provider_name == "qbittorrent":
                                prefix = "💾 [TG Local qBit] [Cached]" if is_cached else "📥 [TG Local qBit] [Download]"
                                title_desc = f"{t['title']}\n"
                                title_desc += f"🟢 Cached (Instant Local Play)" if is_cached else f"📥 Download & Cache to Telegram"
                            else:
                                prefix = "⚡ [TG Debrid] [Cached]" if is_cached else "📥 [TG Debrid] [Download]"
                                title_desc = f"{t['title']}\n"
                                title_desc += f"🟢 Cached (Instant Play)" if is_cached else f"📥 Download & Cache to Telegram"
                            title_desc += f"\n📦 Size: {size_str} | 👥 Seeders: {t['seeders']} | 🔍 Source: {t['source']}"
                            
                            if Config.AUTO_THUYET_MINH:
                                tm_cache_key = hashlib.md5(t['title'].encode("utf-8")).hexdigest()
                                asyncio.create_task(ensure_subtitles_and_tts(tm_cache_key, t['title'], imdb_id=stream_id, media_type=type))
                                
                            streams.append({
                                "name": prefix,
                                "title": title_desc,
                                "url": stream_url,
                                "behaviorHints": {
                                    "notWebReady": True,
                                }
                            })
        except Exception as e:
            logger.error(f"Cinemeta search/resolve failed: {e}")
            
        # 3. MoviesDrive Direct Fast Stream Integration
        try:
            from moviesdrive_router import stream_endpoint as md_stream
            md_resp = await md_stream(request, type, stream_id)
            if hasattr(md_resp, "body"):
                import json
                md_data = json.loads(md_resp.body.decode("utf-8"))
                for s in md_data.get("streams", []):
                    streams.append(s)
        except Exception as e:
            logger.warning(f"Failed to fetch MoviesDrive streams for IMDb {stream_id}: {e}")

        # 4. HDHub4u Direct Fast Stream Integration
        try:
            from hdhub4u_router import stream_endpoint as hdh_stream
            hdh_resp = await hdh_stream(request, type, stream_id)
            if hasattr(hdh_resp, "body"):
                import json
                hdh_data = json.loads(hdh_resp.body.decode("utf-8"))
                for s in hdh_data.get("streams", []):
                    streams.append(s)
        except Exception as e:
            logger.warning(f"Failed to fetch HDHub4u streams for IMDb {stream_id}: {e}")
            
    # Interleave Thuyết Minh AI streams if enabled
    if Config.AUTO_THUYET_MINH and streams:
        tm_streams = []
        for s in streams:
            name = s.get("name", "")
            url = s.get("url", "")
            if not url:
                continue
                
            is_tg_file = "/stream/file/" in url
            is_debrid = "/stream/debrid/" in url
            is_qbit = "/stream/qbittorrent/" in url
            
            if is_tg_file or is_debrid or is_qbit:
                tm_url = url
                if is_tg_file:
                    tm_url = url.replace("/stream/file/", "/stream/thuyetminh/file/")
                elif is_debrid:
                    tm_url = url.replace("/stream/debrid/", "/stream/thuyetminh/debrid/")
                elif is_qbit:
                    tm_url = url.replace("/stream/qbittorrent/", "/stream/thuyetminh/qbittorrent/")
                
                tm_stream = dict(s)
                tm_stream["url"] = tm_url
                
                if "▶" in name:
                    tm_stream["name"] = name.replace("▶", "🎙️ TM AI -")
                elif "⚡" in name:
                    tm_stream["name"] = name.replace("⚡", "🎙️ TM AI - ⚡")
                elif "📥" in name:
                    tm_stream["name"] = name.replace("📥", "🎙️ TM AI - 📥")
                elif "💾" in name:
                    tm_stream["name"] = name.replace("💾", "🎙️ TM AI - 💾")
                else:
                    tm_stream["name"] = "🎙️ TM AI - " + name
                    
                tm_title = s.get("title", "")
                tm_stream["title"] = f"[Thuyết Minh Tiếng Việt AI]\n" + tm_title
                
                # Exclude original subtitles from TM stream as it's already voiced over
                # (but keeping it can also be fine if they want to read along; let's keep them)
                tm_streams.append(tm_stream)
                
        # Interleave them for a better user experience
        interleaved = []
        for s in streams:
            interleaved.append(s)
            for tm_s in tm_streams:
                expected_tm_url = s["url"].replace("/stream/file/", "/stream/thuyetminh/file/").replace("/stream/debrid/", "/stream/thuyetminh/debrid/").replace("/stream/qbittorrent/", "/stream/thuyetminh/qbittorrent/")
                if expected_tm_url == tm_s["url"]:
                    interleaved.append(tm_s)
                    break
        streams = interleaved

    logger.info(f"Returning streams count={len(streams)} names={[s.get('name') for s in streams]}")
    return {"streams": streams}

async def resolve_stream_url_from_cache(video_filename: str, video_size: int = None) -> str:
    stream_data = DEBRID_STREAM_URL_CACHE.get(video_filename)
    if isinstance(stream_data, tuple):
        provider, magnet_link = stream_data
        try:
            debrid_provider = get_debrid_provider()
            if debrid_provider:
                logger.info(f"Resolving Debrid stream URL on-the-fly for {video_filename}...")
                direct_url = await debrid_provider.get_stream_url(magnet_link, video_filename)
                if direct_url:
                    # Update cache to the resolved direct URL string so we don't resolve it again
                    DEBRID_STREAM_URL_CACHE[video_filename] = direct_url
                    return direct_url
        except Exception as e:
            logger.error(f"Failed to resolve Debrid stream URL on-the-fly: {e}")
    elif isinstance(stream_data, str):
        return stream_data

    # Fallback: scan user's Debrid/qBittorrent active downloads for matching file size or filename
    try:
        debrid_provider = get_debrid_provider()
        if debrid_provider and hasattr(debrid_provider, "get_direct_url_by_size"):
            logger.info(f"Searching active torrent downloads for filename: '{video_filename}' (size: {video_size})...")
            direct_url = await debrid_provider.get_direct_url_by_size(video_size, name_hint=video_filename)
            if direct_url:
                logger.info(f"Found direct stream URL for torrent: {direct_url}")
                DEBRID_STREAM_URL_CACHE[video_filename] = direct_url
                return direct_url
    except Exception as e:
        logger.error(f"Failed to find direct stream URL by size/name on Debrid/qBittorrent: {e}")

    return None

@app.get("/subtitles/{type}/{id}.json")
@app.get("/subtitles/{type}/{id}/{extra}.json")
@app.get("/{api_key}/subtitles/{type}/{id}.json")
@app.get("/{api_key}/subtitles/{type}/{id}/{extra}.json")
async def subtitles_handler(
    type: str,
    id: str,
    request: Request,
    extra: str = None,
    api_key: str = ""
):
    if Config.API_KEY:
        actual_key = api_key or request.query_params.get("api_key", "")
        if actual_key != Config.API_KEY:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
    subtitles = []
    actual_key = api_key or request.query_params.get("api_key", "")
    query_param = f"?api_key={actual_key}" if actual_key else ""
    
    # Extract filename and size from extra parameter if present
    video_filename = None
    video_size = None
    if extra:
        decoded_extra = urllib.parse.unquote(extra)
        if "?" in decoded_extra:
            decoded_extra = decoded_extra.split("?", 1)[0]
        params = urllib.parse.parse_qs(decoded_extra)
        if "filename" in params:
            video_filename = params["filename"][0]
        if "videoSize" in params:
            try:
                video_size = int(params["videoSize"][0])
            except ValueError:
                pass
    
    if id.startswith("tgfile_"):
        parts = id.split("_")
        if len(parts) >= 3:
            chat_id = parts[1]
            msg_id = parts[2]
            try:
                try:
                    chat_id_val = int(chat_id)
                except ValueError:
                    chat_id_val = chat_id
                msg = await tg_client_manager.get_message(int(msg_id), chat_id=chat_id_val)
                media = msg.video or msg.document or msg.audio
                fn = getattr(media, "file_name", "") or ""
                if fn:
                    stream_url = f"{Config.ADDON_URL}/stream/file/{chat_id}/{msg_id}/{urllib.parse.quote(fn)}{query_param}"
                    subtitles = await find_subtitles_for_video(fn, api_key=api_key, video_url=stream_url)
            except Exception as e:
                logger.error(f"Failed to resolve subtitles for direct catalog ID {id}: {e}")
                
    elif id.startswith("tt"):
        imdb_id = id
        season = None
        episode = None
        if ":" in id:
            parts = id.split(":")
            imdb_id = parts[0]
            season = int(parts[1])
            episode = int(parts[2])
            
        try:
            if video_filename:
                logger.info(f"Resolving subtitles directly for filename: '{video_filename}'")
                stream_url = None
                try:
                    tg_results = await tg_client_manager.search_messages(query=video_filename, limit=10)
                    for msg in tg_results:
                        media = msg.video or msg.document or msg.audio
                        fn = getattr(media, "file_name", "") or msg.caption or ""
                        if fn == video_filename or video_filename in fn or fn in video_filename:
                            actual_fn = fn if fn else video_filename
                            stream_url = f"{Config.ADDON_URL}/stream/file/{msg.chat.id}/{msg.id}/{urllib.parse.quote(actual_fn)}{query_param}"
                            break
                except Exception as e:
                    logger.error(f"Failed to find video msg in subtitles_handler: {e}")
                
                # Check direct Debrid stream cache if not on Telegram
                if not stream_url:
                    stream_url = await resolve_stream_url_from_cache(video_filename, video_size)
                    
                subtitles = await find_subtitles_for_video(video_filename, api_key=api_key, video_url=stream_url, imdb_id=id, media_type=type)
            else:
                meta = await get_metadata_from_cinemeta(type, imdb_id)
                movie_name = meta.get("name")
                if movie_name:
                    tg_results = await tg_client_manager.search_messages(query=movie_name, limit=50)
                    target_msg = None
                    for msg in tg_results:
                        media = msg.video or msg.document or msg.audio
                        fn = getattr(media, "file_name", "") or msg.caption or ""
                        if type == "series" and not matches_episode(fn, season, episode):
                            continue
                        video_filename = fn
                        target_msg = msg
                        break
                    
                    if video_filename and target_msg:
                        stream_url = f"{Config.ADDON_URL}/stream/file/{target_msg.chat.id}/{target_msg.id}/{urllib.parse.quote(video_filename)}{query_param}"
                        subtitles = await find_subtitles_for_video(video_filename, api_key=api_key, cached_messages=tg_results, video_url=stream_url, imdb_id=id, media_type=type)
        except Exception as e:
            logger.error(f"Failed to resolve subtitles for IMDb ID {id}: {e}")
            
    elif video_filename:
        # Fallback for non-standard IDs (like adult_xxx or magnet links) when filename is provided
        try:
            logger.info(f"Resolving subtitles for non-standard ID {id} via filename: '{video_filename}'")
            stream_url = await resolve_stream_url_from_cache(video_filename, video_size)
            if not stream_url:
                try:
                    tg_results = await tg_client_manager.search_messages(query=video_filename, limit=5)
                    for msg in tg_results:
                        media = msg.video or msg.document or msg.audio
                        fn = getattr(media, "file_name", "") or ""
                        if fn == video_filename:
                            stream_url = f"{Config.ADDON_URL}/stream/file/{msg.chat.id}/{msg.id}/{urllib.parse.quote(video_filename)}{query_param}"
                            break
                except Exception as e:
                    logger.error(f"Failed to search video msg in subtitles_handler: {e}")
            subtitles = await find_subtitles_for_video(video_filename, api_key=api_key, video_url=stream_url, imdb_id=None, media_type=type)
        except Exception as e:
            logger.error(f"Failed to resolve subtitles for custom ID {id}: {e}")
            
    return {"subtitles": subtitles}

@app.api_route("/stream/subtitle/{chat_id}/{message_id}/{filename}", methods=["GET", "HEAD"])
async def tg_subtitle_proxy(
    chat_id: str, 
    message_id: int, 
    filename: str,
    request: Request,
    api_key: str = ""
):
    if Config.API_KEY and api_key != Config.API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    try:
        try:
            chat_id_val = int(chat_id)
        except ValueError:
            chat_id_val = chat_id
        msg = await tg_client_manager.get_message(message_id, chat_id=chat_id_val)
    except Exception as e:
        logger.error(f"Proxy failed to fetch subtitle message: {e}")
        raise HTTPException(status_code=404, detail="Subtitle file not found")
        
    if not msg:
        raise HTTPException(status_code=404, detail="Subtitle message not found")
        
    media = msg.document or msg.audio or msg.video
    if not media:
        raise HTTPException(status_code=404, detail="No media found in subtitle message")
        
    content_type = "text/plain"
    filename_lower = filename.lower()
    if filename_lower.endswith(".srt"):
        content_type = "application/x-subrip"
    elif filename_lower.endswith(".vtt"):
        content_type = "text/vtt"
    elif filename_lower.endswith(".ass"):
        content_type = "text/plain"
        
    headers = {
        "Content-Disposition": f"inline; filename*=UTF-8''{urllib.parse.quote(filename)}",
        "Access-Control-Allow-Origin": "*",
        "Content-Length": str(media.file_size),
    }
    
    if request.method == "HEAD":
        return Response(
            status_code=200,
            media_type=content_type,
            headers=headers
        )
        
    try:
        logger.info(f"Downloading subtitle file from Telegram: {filename} (msg ID {message_id})")
        file_buffer = await tg_client_manager.client.download_media(msg, in_memory=True)
        content = file_buffer.getvalue()
    except Exception as e:
        logger.error(f"Failed to download subtitle file: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve subtitle media")
        
    return Response(
        content=content,
        media_type=content_type,
        headers=headers
    )

@app.api_route("/stream/subtitle/autoviet/{cache_key}", methods=["GET", "HEAD"])
@app.api_route("/{api_key}/stream/subtitle/autoviet/{cache_key}", methods=["GET", "HEAD"])
async def auto_viet_subtitle_endpoint(
    cache_key: str,
    request: Request,
    api_key: str = "",
    source_url: str = None,
    video_url: str = None,
    filename: str = "subtitle.srt"
):
    if Config.API_KEY:
        actual_key = api_key or request.query_params.get("api_key", "")
        if actual_key != Config.API_KEY:
            raise HTTPException(status_code=403, detail="Unauthorized")
            
    q_params = request.query_params
    source_url = q_params.get("source_url")
    video_url = q_params.get("video_url")
    filename = q_params.get("filename", "subtitle.srt")
    
    content_type = "application/x-subrip"
    if filename.lower().endswith(".vtt"):
        content_type = "text/vtt"
        
    headers = {
        "Content-Disposition": f"inline; filename*=UTF-8''{urllib.parse.quote(filename)}",
        "Access-Control-Allow-Origin": "*",
    }
    
    if request.method == "HEAD":
        return Response(
            status_code=200,
            media_type=content_type,
            headers=headers
        )
        
    content, progress = await subtitle_generator.get_or_start_translation(
        cache_key=cache_key,
        source_url=source_url,
        video_url=video_url,
        filename=filename
    )
    
    if not content or not content.strip():
        content = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:05.000\n[Đang tải phụ đề tiếng Việt đồng bộ...]"
        content_type = "text/vtt; charset=utf-8"
        
    if progress < 1.0:
        headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    else:
        headers["Cache-Control"] = "public, max-age=31536000"
        
    return Response(
        content=content.encode("utf-8"),
        media_type=content_type,
        headers=headers
    )

async def get_remote_file_size(url: str) -> int:
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            # 1. Try GET with Range bytes=0-0 (most reliable for CDNs that block HEAD or strip Content-Length on HEAD)
            resp = await client.get(url, headers={"Range": "bytes=0-0"}, follow_redirects=True)
            if resp.status_code in (200, 206):
                content_range = resp.headers.get("Content-Range", "")
                if "/" in content_range:
                    total_size = content_range.split("/")[-1].strip()
                    if total_size.isdigit():
                        return int(total_size)
                content_length = resp.headers.get("Content-Length")
                if content_length and content_length.isdigit():
                    return int(content_length)
    except Exception as e:
        logger.warning(f"Range GET file size check failed: {e}")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.head(url, follow_redirects=True)
            content_length = resp.headers.get("Content-Length")
            if content_length and content_length.isdigit():
                return int(content_length)
    except Exception as e:
        logger.warning(f"HEAD file size check failed: {e}")
        
    return 0

def get_subtitle_duration(cache_key: str) -> float:
    from subtitles_service import CACHE_DIR as SUB_CACHE_DIR, parse_subtitles
    sub_path = os.path.join(SUB_CACHE_DIR, f"{cache_key}.srt")
    if os.path.exists(sub_path):
        try:
            with open(sub_path, "r", encoding="utf-8") as f:
                content = f.read()
            _, blocks = parse_subtitles(content)
            max_time = 0.0
            for b in blocks:
                parts = b["time"].split("-->")
                if len(parts) == 2:
                    end_str = parts[1].strip().replace(",", ".")
                    try:
                        t_parts = end_str.split(":")
                        if len(t_parts) == 3:
                            h, m, s = t_parts
                            t = float(h) * 3600 + float(m) * 60 + float(s)
                        elif len(t_parts) == 2:
                            m, s = t_parts
                            t = float(m) * 60 + float(s)
                        else:
                            t = float(end_str)
                        if t > max_time:
                            max_time = t
                    except Exception:
                        pass
            if max_time > 0:
                return max_time
        except Exception:
            pass
    return 7200.0  # default 2 hours

async def ensure_subtitles_and_tts(cache_key: str, filename: str, imdb_id: str = None, media_type: str = "movie") -> str:
    from tts_service import CACHE_DIR as TTS_CACHE_DIR, tts_manager
    final_pcm_path = os.path.join(TTS_CACHE_DIR, f"{cache_key}_merged.pcm")
    if os.path.exists(final_pcm_path):
        return final_pcm_path
        
    from subtitles_service import CACHE_DIR as SUB_CACHE_DIR
    sub_path = os.path.join(SUB_CACHE_DIR, f"{cache_key}.srt")
    
    if os.path.exists(sub_path) and not os.path.exists(final_pcm_path) and cache_key not in tts_manager.active_tasks:
        try:
            logger.info(f"Sub cached but PCM missing for {cache_key}. Starting TTS generation...")
            with open(sub_path, "r", encoding="utf-8") as f:
                srt_content = f.read()
            await tts_manager.start_tts_generation(cache_key, srt_content)
        except Exception as e:
            logger.error(f"Failed to start TTS from cached sub: {e}")
    if not os.path.exists(sub_path):
        logger.info(f"Subtitle cache miss for '{filename}' ({cache_key}). Fetching on the fly...")
        subtitles = []
        
        if imdb_id:
            try:
                os_subs = await fetch_opensubtitles(imdb_id, media_type)
                for sub in os_subs:
                    lang = sub.get("lang")
                    if lang in ("vie", "vi", "eng"):
                        sub_id_hash = hashlib.md5(sub["url"].encode()).hexdigest()
                        subtitles.append({
                            "url": sub["url"],
                            "lang": "vie" if lang in ("vie", "vi") else "eng"
                        })
            except Exception as e:
                logger.error(f"On-the-fly OpenSubtitles query failed: {e}")
                
        query = get_search_query_from_filename(filename)
        if query:
            try:
                tg_results = await tg_client_manager.search_messages(query=query, limit=20)
                seen_msg_ids = set()
                for msg in tg_results:
                    if msg.id in seen_msg_ids:
                        continue
                    doc = msg.document or msg.audio or msg.video
                    if not doc:
                        continue
                    sub_fn = getattr(doc, "file_name", "") or ""
                    if sub_fn.lower().endswith(('.srt', '.vtt', '.ass')):
                        if matches_subtitle(filename, sub_fn):
                            seen_msg_ids.add(msg.id)
                            query_param = f"?api_key={Config.API_KEY}" if Config.API_KEY else ""
                            subtitles.append({
                                "url": f"{Config.ADDON_URL}/stream/subtitle/{msg.chat.id}/{msg.id}/{urllib.parse.quote(sub_fn)}{query_param}",
                                "lang": "eng"
                            })
            except Exception as e:
                logger.error(f"On-the-fly Telegram subtitle search failed: {e}")

        if subtitles:
            has_vi = any(sub.get("lang") in ("vie", "vi") for sub in subtitles)
            if has_vi:
                vi_sub = next(sub for sub in subtitles if sub.get("lang") in ("vie", "vi"))
                await prepare_existing_vi_sub_and_tts(cache_key, vi_sub["url"])
            elif Config.AUTO_VIET_SUB:
                source_sub = next((s for s in subtitles if s.get("lang") == "eng"), subtitles[0])
                await subtitle_generator.get_or_start_translation(
                    cache_key=cache_key,
                    source_url=source_sub["url"],
                    video_url=None,
                    filename=filename
                )
                
    if os.path.exists(sub_path) or cache_key in tts_manager.active_tasks or cache_key in subtitle_generator.active_tasks:
        logger.info(f"Waiting for merged PCM to be generated for {cache_key}...")
        for _ in range(24):
            if os.path.exists(final_pcm_path):
                return final_pcm_path
            await asyncio.sleep(0.5)
            
    if os.path.exists(final_pcm_path):
        return final_pcm_path
    return ""

async def ffmpeg_stream_generator(ffmpeg_path: str, video_url: str, pcm_path: str, seek_time: float):
    cmd = [
        ffmpeg_path, "-y",
        "-ss", f"{seek_time:.3f}",
        "-i", video_url,
        "-ss", f"{seek_time:.3f}",
        "-f", "s16le",
        "-ar", "24000",
        "-ac", "1",
        "-i", pcm_path,
        "-filter_complex", "[0:a:0][1:a]sidechaincompress=threshold=0.03:ratio=5:attack=100:release=500[ducked]; [ducked][1:a]amix=inputs=2:duration=first:dropout_transition=0[tm_audio]",
        "-map", "0:v:0",
        "-map", "[tm_audio]",
        "-map", "0:a:0",
        "-c:v", "copy",
        "-c:a:0", "aac",
        "-b:a:0", "128k",
        "-c:a:1", "aac",
        "-b:a:1", "128k",
        "-metadata:s:a:0", "language=vie",
        "-metadata:s:a:0", "title=Thuyết Minh AI",
        "-metadata:s:a:1", "language=eng",
        "-metadata:s:a:1", "title=Original Audio",
        "-f", "mpegts",
        "pipe:1"
    ]
    
    logger.info(f"Running FFMPEG Thuyết Minh command: {' '.join(cmd)}")
    
    import subprocess
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL
    )
    try:
        while True:
            chunk = await asyncio.to_thread(proc.stdout.read, 65536)
            if not chunk:
                break
            yield chunk
    except asyncio.CancelledError:
        try:
            proc.terminate()
            await asyncio.to_thread(proc.wait)
        except Exception:
            pass
        raise
    finally:
        try:
            if proc.poll() is None:
                proc.terminate()
                await asyncio.to_thread(proc.wait)
        except Exception:
            pass

@app.api_route("/stream/thuyetminh/file/{chat_id}/{message_id}/{filename}", methods=["GET", "HEAD"])
async def tg_thuyetminh_stream_proxy(
    chat_id: str, 
    message_id: int, 
    filename: str, 
    request: Request,
    api_key: str = ""
):
    if Config.API_KEY and api_key != Config.API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    cache_key = hashlib.md5(filename.encode("utf-8")).hexdigest()
    
    try:
        try:
            chat_id_val = int(chat_id)
        except ValueError:
            chat_id_val = chat_id
        msg = await tg_client_manager.get_message(message_id, chat_id=chat_id_val)
    except Exception as e:
        logger.error(f"Proxy failed to fetch message: {e}")
        raise HTTPException(status_code=404, detail="Media file not found")
        
    if not msg:
        raise HTTPException(status_code=404, detail="Media message not found")
        
    media = msg.video or msg.document or msg.audio
    if not media:
        raise HTTPException(status_code=404, detail="No playable media found in message")
        
    file_size = media.file_size
    mime_type = "video/mp2t"
    
    pcm_path = await ensure_subtitles_and_tts(cache_key, filename)
    
    if not pcm_path:
        logger.warning(f"No TTS audio track found for '{filename}'. Falling back to original stream.")
        original_url = f"{Config.ADDON_URL}/stream/file/{chat_id}/{message_id}/{urllib.parse.quote(filename)}"
        if api_key:
            original_url += f"?api_key={api_key}"
        return RedirectResponse(url=original_url)
        
    range_header = request.headers.get("Range")
    start = 0
    if range_header:
        try:
            bytes_range = range_header.replace("bytes=", "").split("-")
            if bytes_range[0]:
                start = int(bytes_range[0])
        except ValueError:
            pass
            
    duration = get_subtitle_duration(cache_key)
    bitrate = file_size / duration if duration > 0 else 1
    seek_time = start / bitrate
    
    query_param = f"?api_key={api_key}" if api_key else ""
    local_video_url = f"http://127.0.0.1:{Config.PORT}/stream/file/{chat_id}/{message_id}/{urllib.parse.quote(filename)}{query_param}"
    
    ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
    if not os.path.exists(ffmpeg_path) and os.path.exists("ffmpeg.exe"):
        ffmpeg_path = "ffmpeg.exe"
        
    headers = {
        "Content-Range": f"bytes {start}-{file_size - 1}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size - start),
        "Content-Disposition": f"inline; filename*=UTF-8''{urllib.parse.quote(filename)}",
    }
    
    status_code = 206 if range_header else 200
    
    if request.method == "HEAD":
        return Response(
            status_code=status_code,
            media_type=mime_type,
            headers=headers
        )
        
    logger.info(f"Streaming Thuyết Minh media '{filename}' (bytes {start}-) via FFMPEG at seek {seek_time:.2f}s")
    
    return SafeStreamingResponse(
        ffmpeg_stream_generator(ffmpeg_path, local_video_url, pcm_path, seek_time),
        status_code=status_code,
        media_type=mime_type,
        headers=headers
    )

@app.api_route("/stream/thuyetminh/debrid/{provider}/{magnet_base64}/{filename}", methods=["GET", "HEAD"])
async def debrid_thuyetminh_stream_proxy(
    provider: str,
    magnet_base64: str,
    filename: str,
    request: Request,
    api_key: str = ""
):
    if Config.API_KEY:
        actual_key = api_key or request.query_params.get("api_key", "")
        if actual_key != Config.API_KEY:
            raise HTTPException(status_code=403, detail="Unauthorized")
            
    cache_key = hashlib.md5(filename.encode("utf-8")).hexdigest()
    
    import base64
    try:
        magnet_link = base64.b64decode(magnet_base64.encode()).decode()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid magnet base64")
        
    debrid_provider = get_debrid_provider()
    if not debrid_provider:
        raise HTTPException(status_code=500, detail="Debrid provider not configured")
        
    direct_url = await debrid_provider.get_stream_url(magnet_link, filename)
    if not direct_url:
        raise HTTPException(status_code=504, detail="Failed to retrieve direct stream URL")
        
    if direct_url.startswith("qbittorrent://"):
        info_hash = direct_url.replace("qbittorrent://", "")
        imdb_id = request.query_params.get("imdb", "")
        local_stream_url = f"{Config.ADDON_URL}/stream/thuyetminh/qbittorrent/{info_hash}/{urllib.parse.quote(filename)}"
        params = []
        if imdb_id:
            params.append(f"imdb={imdb_id}")
        if api_key:
            params.append(f"api_key={api_key}")
        if params:
            local_stream_url += "?" + "&".join(params)
        logger.info(f"Redirecting player to local qBittorrent Thuyết Minh stream: {local_stream_url}")
        return RedirectResponse(url=local_stream_url, status_code=302)
        
    imdb_id = request.query_params.get("imdb", "")
    media_type = "series" if ":" in imdb_id else "movie"
    pcm_path = await ensure_subtitles_and_tts(cache_key, filename, imdb_id=imdb_id, media_type=media_type)
    
    if not pcm_path:
        logger.warning(f"No TTS audio track found for '{filename}'. Redirecting to direct Debrid stream.")
        return RedirectResponse(url=direct_url)
        
    file_size = await get_remote_file_size(direct_url)
    if not file_size:
        return RedirectResponse(url=direct_url)
        
    mime_type = "video/mp2t"
    
    range_header = request.headers.get("Range")
    start = 0
    if range_header:
        try:
            bytes_range = range_header.replace("bytes=", "").split("-")
            if bytes_range[0]:
                start = int(bytes_range[0])
        except ValueError:
            pass
            
    duration = get_subtitle_duration(cache_key)
    bitrate = file_size / duration if duration > 0 else 1
    seek_time = start / bitrate
    
    ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
    if not os.path.exists(ffmpeg_path) and os.path.exists("ffmpeg.exe"):
        ffmpeg_path = "ffmpeg.exe"
        
    headers = {
        "Content-Range": f"bytes {start}-{file_size - 1}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size - start),
        "Content-Disposition": f"inline; filename*=UTF-8''{urllib.parse.quote(filename)}",
    }
    
    status_code = 206 if range_header else 200
    
    if request.method == "HEAD":
        return Response(
            status_code=status_code,
            media_type=mime_type,
            headers=headers
        )
        
    logger.info(f"Streaming Thuyết Minh Debrid media '{filename}' (bytes {start}-) at seek {seek_time:.2f}s")
    
    return SafeStreamingResponse(
        ffmpeg_stream_generator(ffmpeg_path, direct_url, pcm_path, seek_time),
        status_code=status_code,
        media_type=mime_type,
        headers=headers
    )

@app.api_route("/stream/thuyetminh/qbittorrent/{info_hash}/{filename}", methods=["GET", "HEAD"])
async def qbittorrent_thuyetminh_stream_proxy(
    info_hash: str,
    filename: str,
    request: Request,
    api_key: str = ""
):
    if Config.API_KEY and api_key != Config.API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    cache_key = hashlib.md5(filename.encode("utf-8")).hexdigest()
    imdb_id = request.query_params.get("imdb", "")
    media_type = "series" if ":" in imdb_id else "movie"
    
    pcm_path = await ensure_subtitles_and_tts(cache_key, filename, imdb_id=imdb_id, media_type=media_type)
    
    if not pcm_path:
        logger.warning(f"No TTS audio track found for '{filename}'. Falling back to original local qBit stream.")
        original_url = f"{Config.ADDON_URL}/stream/qbittorrent/{info_hash}/{urllib.parse.quote(filename)}"
        params = []
        if imdb_id:
            params.append(f"imdb={imdb_id}")
        if api_key:
            params.append(f"api_key={api_key}")
        if params:
            original_url += "?" + "&".join(params)
        return RedirectResponse(url=original_url)
        
    debrid_provider = get_debrid_provider()
    from debrid import QBittorrentProvider
    if not isinstance(debrid_provider, QBittorrentProvider):
        raise HTTPException(status_code=400, detail="qBittorrent is not the active Debrid provider")
        
    files = await debrid_provider.get_torrent_files(info_hash)
    if not files:
        raise HTTPException(status_code=404, detail="Torrent files not found in qBit")
        
    target_file = None
    decoded_fn = urllib.parse.unquote(filename).lower()
    for f in files:
        if decoded_fn in f.get("name", "").lower():
            target_file = f
            break
            
    if not target_file:
        video_files = [f for f in files if f.get("name", "").lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm', '.ts'))]
        if video_files:
            video_files.sort(key=lambda x: x.get("size", 0), reverse=True)
            target_file = video_files[0]
            
    if not target_file:
        target_file = files[0]
        
    file_size = target_file["size"]
    mime_type = "video/mp2t"
    
    range_header = request.headers.get("Range")
    start = 0
    if range_header:
        try:
            bytes_range = range_header.replace("bytes=", "").split("-")
            if bytes_range[0]:
                start = int(bytes_range[0])
        except ValueError:
            pass
            
    duration = get_subtitle_duration(cache_key)
    bitrate = file_size / duration if duration > 0 else 1
    seek_time = start / bitrate
    
    query_param = []
    if imdb_id:
        query_param.append(f"imdb={imdb_id}")
    if api_key:
        query_param.append(f"api_key={api_key}")
    q_str = "?" + "&".join(query_param) if query_param else ""
    local_video_url = f"http://127.0.0.1:{Config.PORT}/stream/qbittorrent/{info_hash}/{urllib.parse.quote(filename)}{q_str}"
    
    ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
    if not os.path.exists(ffmpeg_path) and os.path.exists("ffmpeg.exe"):
        ffmpeg_path = "ffmpeg.exe"
        
    headers = {
        "Content-Range": f"bytes {start}-{file_size - 1}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size - start),
        "Content-Disposition": f"inline; filename*=UTF-8''{urllib.parse.quote(os.path.basename(target_file['name']))}",
    }
    
    status_code = 206 if range_header else 200
    
    if request.method == "HEAD":
        return Response(
            status_code=status_code,
            media_type=mime_type,
            headers=headers
        )
        
    logger.info(f"Streaming Thuyết Minh Local qBit media '{filename}' (bytes {start}-) via FFMPEG at seek {seek_time:.2f}s")
    
    return SafeStreamingResponse(
        ffmpeg_stream_generator(ffmpeg_path, local_video_url, pcm_path, seek_time),
        status_code=status_code,
        media_type=mime_type,
        headers=headers
    )

@app.api_route("/stream/file/{chat_id}/{message_id}/{filename}", methods=["GET", "HEAD"])
async def tg_stream_proxy(
    chat_id: str, 
    message_id: int, 
    filename: str, 
    request: Request,
    api_key: str = ""
):
    if Config.API_KEY and api_key != Config.API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    cache_key = hashlib.md5(filename.encode("utf-8")).hexdigest()
    subtitle_generator.register_video_url(cache_key, str(request.url))
        
    try:
        try:
            chat_id_val = int(chat_id)
        except ValueError:
            chat_id_val = chat_id
        msg = await tg_client_manager.get_message(message_id, chat_id=chat_id_val)
    except Exception as e:
        logger.error(f"Proxy failed to fetch message: {e}")
        raise HTTPException(status_code=404, detail="Media file not found")
        
    if not msg:
        raise HTTPException(status_code=404, detail="Media message not found")
        
    media = msg.video or msg.document or msg.audio
    if not media:
        raise HTTPException(status_code=404, detail="No playable media found in message")
        
    file_size = media.file_size
    mime_type = media.mime_type or "video/mp4"
    
    if request.method == "GET":
        asyncio.create_task(
            tg_client_manager.send_play_log(filename, chat_id_val, message_id)
        )
    
    range_header = request.headers.get("Range")
    start = 0
    end = file_size - 1
    
    if range_header:
        try:
            bytes_range = range_header.replace("bytes=", "").split("-")
            if bytes_range[0]:
                start = int(bytes_range[0])
            if len(bytes_range) > 1 and bytes_range[1]:
                end = int(bytes_range[1])
        except ValueError:
            pass
            
    content_length = end - start + 1
    
    chunk_size = 1024 * 1024
    offset = start // chunk_size
    skip_bytes = start % chunk_size
    
    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Disposition": f"inline; filename*=UTF-8''{urllib.parse.quote(filename)}",
    }
    
    status_code = 206 if range_header else 200
    
    if request.method == "HEAD":
        logger.info(f"HEAD request for media '{filename}' (bytes {start}-{end}/{file_size}) - Status {status_code}")
        return Response(
            status_code=status_code,
            media_type=mime_type,
            headers=headers
        )
        
    async def file_generator():
        bytes_sent = 0
        bytes_to_skip = skip_bytes
        try:
            async for chunk in tg_client_manager.client.stream_media(media, offset=offset):
                if bytes_to_skip > 0:
                    if bytes_to_skip < len(chunk):
                        chunk = chunk[bytes_to_skip:]
                        bytes_to_skip = 0
                    else:
                        bytes_to_skip -= len(chunk)
                        continue
                        
                if bytes_sent + len(chunk) > content_length:
                    chunk = chunk[:content_length - bytes_sent]
                    
                yield chunk
                bytes_sent += len(chunk)
                
                if bytes_sent >= content_length:
                    break
        except (asyncio.CancelledError, GeneratorExit):
            pass
        except Exception as e:
            logger.error(f"Streaming error on message {message_id}: {e}")
            
    logger.info(f"Streaming media '{filename}' (bytes {start}-{end}/{file_size}) - Status {status_code}")
    
    return SafeStreamingResponse(
        file_generator(),
        status_code=status_code,
        media_type=mime_type,
        headers=headers
    )

@app.api_route("/stream/split/{chat_id}/{message_ids}/{filename}", methods=["GET", "HEAD"])
async def tg_split_stream_proxy(
    chat_id: str, 
    message_ids: str, 
    filename: str, 
    request: Request,
    api_key: str = ""
):
    if Config.API_KEY and api_key != Config.API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    cache_key = hashlib.md5(filename.encode("utf-8")).hexdigest()
    subtitle_generator.register_video_url(cache_key, str(request.url))
        
    msg_id_list = [int(x) for x in message_ids.split(",") if x.strip().isdigit()]
    if not msg_id_list:
        raise HTTPException(status_code=400, detail="Invalid message IDs")
        
    try:
        chat_id_val = int(chat_id)
    except ValueError:
        chat_id_val = chat_id
        
    if request.method == "GET":
        asyncio.create_task(
            tg_client_manager.send_play_log(filename, chat_id_val, msg_id_list[0])
        )
        
    chunks_info = []
    total_size = 0
    
    for msg_id in msg_id_list:
        try:
            msg = await tg_client_manager.get_message(msg_id, chat_id=chat_id_val)
            if not msg:
                raise HTTPException(status_code=404, detail=f"Message {msg_id} not found")
            media = msg.video or msg.document or msg.audio
            if not media:
                raise HTTPException(status_code=400, detail=f"No media in message {msg_id}")
                
            chunks_info.append({
                "media": media,
                "size": media.file_size,
                "start_byte": total_size,
                "end_byte": total_size + media.file_size - 1
            })
            total_size += media.file_size
        except Exception as e:
            logger.error(f"Error fetching metadata for msg {msg_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed resolving split file metadata")
            
    range_header = request.headers.get("Range")
    start = 0
    end = total_size - 1
    
    if range_header:
        try:
            bytes_range = range_header.replace("bytes=", "").split("-")
            if bytes_range[0]:
                start = int(bytes_range[0])
            if len(bytes_range) > 1 and bytes_range[1]:
                end = int(bytes_range[1])
        except ValueError:
            pass
            
    content_length = end - start + 1
    mime_type = chunks_info[0]["media"].mime_type or "video/mp4"
    
    headers = {
        "Content-Range": f"bytes {start}-{end}/{total_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Disposition": f"inline; filename*=UTF-8''{urllib.parse.quote(filename)}",
    }
    
    status_code = 206 if range_header else 200
    
    if request.method == "HEAD":
        return Response(
            status_code=status_code,
            media_type=mime_type,
            headers=headers
        )
        
    async def split_file_generator():
        bytes_sent = 0
        block_size = 1024 * 1024  # 1 MB blocks
        
        for chunk in chunks_info:
            c_start = chunk["start_byte"]
            c_end = chunk["end_byte"]
            
            if c_end < start or c_start > end:
                continue
                
            read_start = max(c_start, start)
            read_end = min(c_end, end)
            chunk_read_len = read_end - read_start + 1
            
            local_offset = read_start - c_start
            offset_blocks = local_offset // block_size
            skip_bytes = local_offset % block_size
            
            chunk_bytes_sent = 0
            bytes_to_skip = skip_bytes
            
            try:
                async for block in tg_client_manager.client.stream_media(chunk["media"], offset=offset_blocks):
                    if bytes_to_skip > 0:
                        if bytes_to_skip < len(block):
                            block = block[bytes_to_skip:]
                            bytes_to_skip = 0
                        else:
                            bytes_to_skip -= len(block)
                            continue
                            
                    if chunk_bytes_sent + len(block) > chunk_read_len:
                        block = block[:chunk_read_len - chunk_bytes_sent]
                        
                    yield block
                    chunk_bytes_sent += len(block)
                    bytes_sent += len(block)
                    
                    if chunk_bytes_sent >= chunk_read_len:
                        break
            except Exception as e:
                logger.error(f"Error streaming split chunk: {e}")
                break
                
            if bytes_sent >= content_length:
                break
                
    logger.info(f"Streaming split media '{filename}' (bytes {start}-{end}/{total_size}) - Status {status_code}")
    
    return SafeStreamingResponse(
        split_file_generator(),
        status_code=status_code,
        media_type=mime_type,
        headers=headers
    )

@app.api_route("/stream/zip/{chat_id}/{message_ids}/{filename}", methods=["GET", "HEAD"])
async def tg_zip_stream_proxy(
    chat_id: str,
    message_ids: str,
    filename: str,
    request: Request,
    api_key: str = ""
):
    if Config.API_KEY and api_key != Config.API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    cache_key = hashlib.md5(filename.encode("utf-8")).hexdigest()
    subtitle_generator.register_video_url(cache_key, str(request.url))
        
    msg_id_list = [int(x) for x in message_ids.split(",") if x.strip().isdigit()]
    if not msg_id_list:
        raise HTTPException(status_code=400, detail="Invalid message IDs")
        
    try:
        chat_id_val = int(chat_id)
    except ValueError:
        chat_id_val = chat_id
        
    if request.method == "GET":
        asyncio.create_task(
            tg_client_manager.send_play_log(filename, chat_id_val, msg_id_list[0])
        )
        
    messages = []
    for msg_id in msg_id_list:
        msg = await tg_client_manager.get_message(msg_id, chat_id=chat_id_val)
        if msg:
            messages.append(msg)
            
    if not messages:
        raise HTTPException(status_code=404, detail="Messages not found")
        
    zip_entries = await list_zip_files(tg_client_manager.client, messages)
    target_entry = None
    for entry in zip_entries:
        if entry.filename == filename:
            target_entry = entry
            break
            
    if not target_entry:
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found in ZIP archive")
        
    file_size = target_entry.file_size
    mime_type = "video/mp4"
    filename_lower = filename.lower()
    if filename_lower.endswith(".mkv"):
        mime_type = "video/x-matroska"
    elif filename_lower.endswith(".mp4"):
        mime_type = "video/mp4"
    elif filename_lower.endswith(".avi"):
        mime_type = "video/x-msvideo"
        
    range_header = request.headers.get("Range")
    start = 0
    end = file_size - 1
    
    if range_header:
        try:
            bytes_range = range_header.replace("bytes=", "").split("-")
            if bytes_range[0]:
                start = int(bytes_range[0])
            if len(bytes_range) > 1 and bytes_range[1]:
                end = int(bytes_range[1])
        except ValueError:
            pass
            
    content_length = end - start + 1
    
    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Disposition": f"inline; filename*=UTF-8''{urllib.parse.quote(filename)}",
    }
    
    status_code = 206 if range_header else 200
    
    if request.method == "HEAD":
        return Response(
            status_code=status_code,
            media_type=mime_type,
            headers=headers
        )
        
    import zipfile
    if target_entry.compress_type == zipfile.ZIP_STORED:
        logger.info(f"ZIP entry '{filename}' is STORED (uncompressed). Using direct offset proxy.")
        reader = TelegramSeekableReader(tg_client_manager.client, messages)
        data_start = await get_zip_entry_data_offset(reader, target_entry.header_offset)
        
        stream_start = data_start + start
        stream_end = data_start + end
        stream_len = stream_end - stream_start + 1
        
        chunks_info = []
        total_size = 0
        
        for part in reader.parts:
            chunks_info.append({
                "media": part["media"],
                "size": part["size"],
                "start_byte": part["start"],
                "end_byte": part["end"] - 1
            })
            total_size += part["size"]
            
        async def split_file_generator():
            bytes_sent = 0
            block_size = 1024 * 1024
            
            for chunk in chunks_info:
                c_start = chunk["start_byte"]
                c_end = chunk["end_byte"]
                
                if c_end < stream_start or c_start > stream_end:
                    continue
                    
                read_start = max(c_start, stream_start)
                read_end = min(c_end, stream_end)
                chunk_read_len = read_end - read_start + 1
                
                local_offset = read_start - c_start
                offset_blocks = local_offset // block_size
                skip_bytes = local_offset % block_size
                
                chunk_bytes_sent = 0
                bytes_to_skip = skip_bytes
                
                try:
                    async for block in tg_client_manager.client.stream_media(chunk["media"], offset=offset_blocks):
                        if bytes_to_skip > 0:
                            if bytes_to_skip < len(block):
                                block = block[bytes_to_skip:]
                                bytes_to_skip = 0
                            else:
                                bytes_to_skip -= len(block)
                                continue
                                
                        if chunk_bytes_sent + len(block) > chunk_read_len:
                            block = block[:chunk_read_len - chunk_bytes_sent]
                            
                        yield block
                        chunk_bytes_sent += len(block)
                        bytes_sent += len(block)
                        
                        if chunk_bytes_sent >= chunk_read_len:
                            break
                except Exception as e:
                    logger.error(f"Error streaming split ZIP chunk: {e}")
                    break
                    
                if bytes_sent >= stream_len:
                    break
                    
        logger.info(f"Streaming uncompressed ZIP entry '{filename}' (raw bytes {stream_start}-{stream_end}/{total_size}) - Status {status_code}")
        return SafeStreamingResponse(
            split_file_generator(),
            status_code=status_code,
            media_type=mime_type,
            headers=headers
        )
    else:
        logger.info(f"ZIP entry '{filename}' is COMPRESSED (type {target_entry.compress_type}). Streaming on-the-fly decompression.")
        reader = TelegramSeekableReader(tg_client_manager.client, messages)
        return SafeStreamingResponse(
            zip_compressed_generator(reader, filename, start, end),
            status_code=status_code,
            media_type=mime_type,
            headers=headers
        )


def _extract_hash_from_magnet(magnet: str) -> str:
    if not magnet:
        return ""
    m = re.search(r'xt=urn:btih:([a-zA-Z0-9]+)', magnet)
    if m:
        return m.group(1).lower()
    return ""


upload_semaphore = asyncio.Semaphore(1)

async def _prepare_telegram_thumbnail(poster_url: str) -> str:
    """
    Downloads the poster image and resizes it to a maximum of 320px for Telegram thumbnails.
    Returns the local path of the prepared thumbnail, or None if failed.
    """
    if not poster_url:
        return None
        
    import tempfile
    import os
    import httpx
    import hashlib
    
    try:
        temp_dir = "temp_cache"
        os.makedirs(temp_dir, exist_ok=True)
        h = hashlib.md5(poster_url.encode()).hexdigest()
        raw_thumb_path = os.path.join(temp_dir, f"raw_thumb_{h}")
        final_thumb_path = os.path.join(temp_dir, f"thumb_{h}.jpg")
        
        if os.path.exists(final_thumb_path):
            return final_thumb_path
            
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(poster_url)
            if resp.status_code == 200:
                with open(raw_thumb_path, "wb") as f:
                    f.write(resp.content)
            else:
                return None
                
        try:
            from PIL import Image
            with Image.open(raw_thumb_path) as img:
                img.thumbnail((320, 320))
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(final_thumb_path, "JPEG", quality=85)
            os.remove(raw_thumb_path)
            return final_thumb_path
        except ImportError:
            os.rename(raw_thumb_path, final_thumb_path)
            return final_thumb_path
    except Exception as e:
        logger.warning(f"Failed to prepare thumbnail: {e}")
        return None


async def _build_rich_caption(imdb_id: str, filename: str) -> tuple:
    """
    Returns (caption_text, poster_url)
    """
    caption = f"📥 Cached via Telegram Debrid\n🎥 {filename}"
    poster_url = None
    
    if imdb_id:
        try:
            meta = await get_metadata_from_cinemeta("movie", imdb_id)
            if not meta.get("name"):
                meta = await get_metadata_from_cinemeta("series", imdb_id)
                
            if meta.get("name"):
                name = meta["name"]
                year = meta.get("year", "")
                genres = ", ".join(meta.get("genres", []))
                poster_url = meta.get("poster")
                
                caption = f"🎥 **{name}**"
                if year:
                    caption += f" ({year})"
                caption += "\n"
                if genres:
                    caption += f"🎭 **Genres:** {genres}\n"
                caption += f"📁 **File:** `{filename}`\n\n"
                caption += "📥 Cached via Telegram Debrid"
        except Exception as e:
            logger.warning(f"Failed building rich caption: {e}")
            
    return caption, poster_url


async def cache_to_telegram_task(direct_url: str, filename: str, imdb_id: str = ""):
    """
    Downloads the file from the direct Debrid URL and uploads it to the Telegram channel.
    This runs entirely in the background under upload_semaphore control.
    """
    try:
        existing = await tg_client_manager.search_messages(query=filename, limit=5)
        for msg in existing:
            media = msg.video or msg.document or msg.audio
            if media:
                fn = getattr(media, "file_name", "") or ""
                if fn == filename:
                    logger.info(f"File '{filename}' already exists in Telegram channel. Skipping upload cache.")
                    return
    except Exception as e:
        logger.warning(f"Error checking existing files in channel: {e}")

    logger.info(f"Background Cache: File '{filename}' is waiting for upload slot...")
    async with upload_semaphore:
        logger.info(f"Background Cache: Starting download of '{filename}' from Debrid...")
        
        import os
        import httpx
        
        temp_dir = "temp_cache"
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, filename)
        
        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                async with client.stream("GET", direct_url) as response:
                    if response.status_code != 200:
                        logger.error(f"Failed to download file from Debrid (HTTP {response.status_code})")
                        return
                    with open(temp_path, "wb") as f:
                        async for chunk in response.iter_bytes(chunk_size=1024*1024):
                            f.write(chunk)
                            
            logger.info(f"Background Cache: Download complete. Uploading '{filename}' to Telegram...")
            
            channel_ids = tg_client_manager.get_channel_ids()
            if not channel_ids:
                logger.error("No Telegram channels configured for caching upload")
                return
                
            target_chat = channel_ids[0]
            caption, poster_url = await _build_rich_caption(imdb_id, filename)
            thumb_path = await _prepare_telegram_thumbnail(poster_url)
            
            ext = filename.lower()
            if ext.endswith(('.mp4', '.mkv', '.webm')):
                await tg_client_manager.client.send_video(
                    chat_id=target_chat,
                    video=temp_path,
                    file_name=filename,
                    thumb=thumb_path,
                    supports_streaming=True,
                    caption=caption
                )
            else:
                await tg_client_manager.client.send_document(
                    chat_id=target_chat,
                    document=temp_path,
                    file_name=filename,
                    thumb=thumb_path,
                    caption=caption
                )
                
            logger.info(f"Background Cache: File '{filename}' uploaded successfully to Telegram chat {target_chat}!")
            
            if Config.LOG_CHANNEL_ID:
                try:
                    await tg_client_manager.client.send_message(
                        chat_id=Config.LOG_CHANNEL_ID,
                        text=f"📥 **Torrent Cached to Telegram**\n\n📁 **File Name:** `{filename}`\n💬 **Target Channel:** `{target_chat}`"
                    )
                except Exception as e:
                    logger.error(f"Failed to send background cache log to log channel: {e}")
                    
            await asyncio.sleep(5.0)
                    
        except Exception as e:
            logger.error(f"Error in background cache task for '{filename}': {e}")
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temp file '{temp_path}': {e}")


@app.get("/stream/debrid/{provider}/{magnet_base64}/{filename}")
async def debrid_stream_proxy(
    provider: str,
    magnet_base64: str,
    filename: str,
    request: Request,
    api_key: str = ""
):
    if Config.API_KEY:
        actual_key = api_key or request.query_params.get("api_key", "")
        if actual_key != Config.API_KEY:
            raise HTTPException(status_code=403, detail="Unauthorized")
            
    cache_key = hashlib.md5(filename.encode("utf-8")).hexdigest()
    subtitle_generator.register_video_url(cache_key, str(request.url))
            
    import base64
    try:
        magnet_link = base64.b64decode(magnet_base64.encode()).decode()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid magnet base64")
        
    debrid_provider = get_debrid_provider()
    if not debrid_provider:
        raise HTTPException(status_code=500, detail="Debrid provider not configured")
        
    logger.info(f"Resolving Debrid stream for torrent: '{filename}'")
    direct_url = await debrid_provider.get_stream_url(magnet_link, filename)
    if not direct_url:
        raise HTTPException(status_code=504, detail="Failed to retrieve direct stream URL from Debrid")
        
    # Cache the resolved Debrid direct URL for subtitles/audio transcription
    DEBRID_STREAM_URL_CACHE[filename] = direct_url
        
    if direct_url.startswith("qbittorrent://"):
        info_hash = direct_url.replace("qbittorrent://", "")
        imdb_id = request.query_params.get("imdb", "")
        local_stream_url = f"{Config.ADDON_URL}/stream/qbittorrent/{info_hash}/{urllib.parse.quote(filename)}"
        params = []
        if imdb_id:
            params.append(f"imdb={imdb_id}")
        if api_key:
            params.append(f"api_key={api_key}")
        if params:
            local_stream_url += "?" + "&".join(params)
        logger.info(f"Redirecting player to local qBittorrent stream: {local_stream_url}")
        return RedirectResponse(url=local_stream_url, status_code=302)
        
    if Config.AUTO_UPLOAD_TO_TELEGRAM:
        imdb_id = request.query_params.get("imdb", "")
        asyncio.create_task(
            cache_to_telegram_task(direct_url, filename, imdb_id)
        )
        
    logger.info(f"Redirecting player to direct Debrid stream: {direct_url}")
    return RedirectResponse(url=direct_url, status_code=302)


_active_qbit_monitors = set()

async def monitor_and_cache_qbit_task(info_hash: str, file_path: str, filename: str, qbit_client, imdb_id: str = ""):
    """
    Monitors qBittorrent download status until 100% complete, uploads to Telegram, and cleans up.
    """
    if info_hash in _active_qbit_monitors:
        return
    _active_qbit_monitors.add(info_hash)
    
    logger.info(f"Background Monitor: Started monitoring local qBit download for hash: {info_hash}")
    
    try:
        import os
        is_completed = False
        for _ in range(960):
            torrent_info = await qbit_client.get_torrent_info(info_hash)
            if not torrent_info:
                logger.warning(f"Background Monitor: Torrent {info_hash} deleted from qBit. Stopping.")
                return
                
            progress = torrent_info.get("progress", 0)
            if progress >= 1.0:
                is_completed = True
                break
                
            state = torrent_info.get("state", "")
            if "error" in state.lower() or "missing" in state.lower():
                logger.error(f"Background Monitor: Torrent {info_hash} entered error state ({state}). Stopping.")
                return
                
            await asyncio.sleep(15.0)
            
        if not is_completed:
            logger.warning(f"Background Monitor: Torrent {info_hash} did not complete within 4 hours. Stopping.")
            return

        await asyncio.sleep(3.0)
        if not os.path.exists(file_path):
            logger.error(f"Background Monitor: Completed file not found at path: {file_path}")
            return

        try:
            existing = await tg_client_manager.search_messages(query=filename, limit=5)
            for msg in existing:
                media = msg.video or msg.document or msg.audio
                if media:
                    fn = getattr(media, "file_name", "") or ""
                    if fn == filename:
                        logger.info(f"Background Monitor: File '{filename}' already exists in Telegram. Deleting local torrent.")
                        await qbit_client.delete_torrent(info_hash, delete_files=True)
                        return
        except Exception as e:
            logger.warning(f"Background Monitor: Error checking existing files in channel: {e}")

        logger.info(f"Background Monitor: Completed download. File '{filename}' is waiting for upload slot...")
        async with upload_semaphore:
            logger.info(f"Background Monitor: Uploading completed file '{filename}' to Telegram channel...")
            channel_ids = tg_client_manager.get_channel_ids()
            if not channel_ids:
                logger.error("No Telegram channels configured for caching upload")
                return
                
            target_chat = channel_ids[0]
            caption, poster_url = await _build_rich_caption(imdb_id, filename)
            thumb_path = await _prepare_telegram_thumbnail(poster_url)
            
            ext = filename.lower()
            if ext.endswith(('.mp4', '.mkv', '.webm')):
                await tg_client_manager.client.send_video(
                    chat_id=target_chat,
                    video=file_path,
                    file_name=filename,
                    thumb=thumb_path,
                    supports_streaming=True,
                    caption=caption
                )
            else:
                await tg_client_manager.client.send_document(
                    chat_id=target_chat,
                    document=file_path,
                    file_name=filename,
                    thumb=thumb_path,
                    caption=caption
                )
                
            logger.info(f"Background Monitor: File '{filename}' uploaded successfully to Telegram! Deleting local torrent.")
            
            await qbit_client.delete_torrent(info_hash, delete_files=True)
            
            if Config.LOG_CHANNEL_ID:
                try:
                    await tg_client_manager.client.send_message(
                        chat_id=Config.LOG_CHANNEL_ID,
                        text=f"📥 **Torrent Cached from Local qBit**\n\n📁 **File Name:** `{filename}`\n💬 **Target Channel:** `{target_chat}`"
                    )
                except Exception as e:
                    logger.error(f"Failed to send qBit cache log to log channel: {e}")
                    
            await asyncio.sleep(5.0)
                
    except Exception as e:
        logger.error(f"Error in monitor task for '{filename}': {e}")
    finally:
        _active_qbit_monitors.discard(info_hash)


async def local_file_generator(file_path: str, start_byte: int, end_byte: int, info_hash: str, qbit_client):
    import os
    chunk_size = 64 * 1024  # 64 KB chunks
    bytes_sent = 0
    content_length = end_byte - start_byte + 1
    curr_pos = start_byte

    while bytes_sent < content_length:
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            if file_size > curr_pos:
                read_len = min(chunk_size, file_size - curr_pos, content_length - bytes_sent)
                with open(file_path, "rb") as f:
                    f.seek(curr_pos)
                    data = f.read(read_len)
                if data:
                    yield data
                    bytes_sent += len(data)
                    curr_pos += len(data)
                    continue

        torrent_info = await qbit_client.get_torrent_info(info_hash)
        if not torrent_info:
            logger.warning("Torrent deleted during local stream. Aborting.")
            break
            
        state = torrent_info.get("state", "")
        if "error" in state.lower() or "missing" in state.lower():
            logger.error(f"Torrent error state: {state}. Aborting stream.")
            break

        await asyncio.sleep(1.0)


@app.api_route("/stream/qbittorrent/{info_hash}/{filename}", methods=["GET", "HEAD"])
async def qbittorrent_stream_proxy(
    info_hash: str,
    filename: str,
    request: Request,
    api_key: str = ""
):
    if Config.API_KEY:
        actual_key = api_key or request.query_params.get("api_key", "")
        if actual_key != Config.API_KEY:
            raise HTTPException(status_code=403, detail="Unauthorized")
            
    cache_key = hashlib.md5(filename.encode("utf-8")).hexdigest()
    subtitle_generator.register_video_url(cache_key, str(request.url))
            
    debrid_provider = get_debrid_provider()
    from debrid import QBittorrentProvider
    if not isinstance(debrid_provider, QBittorrentProvider):
        raise HTTPException(status_code=400, detail="qBittorrent is not the active Debrid provider")
        
    torrent_info = {}
    files = []
    import os
    for _ in range(10):
        torrent_info = await debrid_provider.get_torrent_info(info_hash)
        if torrent_info:
            files = await debrid_provider.get_torrent_files(info_hash)
            if files:
                break
        await asyncio.sleep(1.5)
        
    if not torrent_info or not files:
        raise HTTPException(status_code=404, detail="Torrent metadata not found in qBittorrent")
        
    target_file = None
    decoded_fn = urllib.parse.unquote(filename).lower()
    for f in files:
        if decoded_fn in f.get("name", "").lower():
            target_file = f
            break
            
    if not target_file:
        video_files = [f for f in files if f.get("name", "").lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm', '.ts'))]
        if video_files:
            video_files.sort(key=lambda x: x.get("size", 0), reverse=True)
            target_file = video_files[0]
            
    if not target_file:
        target_file = files[0]
        
    save_dir = Config.QBITTORRENT_PLAY_DIR or torrent_info.get("save_path", "")
    file_path = os.path.join(save_dir, target_file["name"])
    
    file_size = target_file["size"]
    mime_type = "video/mp4"
    if target_file["name"].lower().endswith(".mkv"):
        mime_type = "video/x-matroska"
        
    range_header = request.headers.get("Range")
    start = 0
    end = file_size - 1
    
    if range_header:
        try:
            bytes_range = range_header.replace("bytes=", "").split("-")
            if bytes_range[0]:
                start = int(bytes_range[0])
            if len(bytes_range) > 1 and bytes_range[1]:
                end = int(bytes_range[1])
        except ValueError:
            pass
            
    content_length = end - start + 1
    
    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Disposition": f"inline; filename*=UTF-8''{urllib.parse.quote(os.path.basename(target_file['name']))}",
    }
    
    status_code = 206 if range_header else 200
    
    if request.method == "HEAD":
        return Response(
            status_code=status_code,
            media_type=mime_type,
            headers=headers
        )
        
    logger.info(f"Local qBit streaming '{target_file['name']}' (bytes {start}-{end}/{file_size}) - Status {status_code}")
    
    if Config.AUTO_UPLOAD_TO_TELEGRAM:
        imdb_id = request.query_params.get("imdb", "")
        asyncio.create_task(
            monitor_and_cache_qbit_task(info_hash, file_path, os.path.basename(target_file['name']), debrid_provider, imdb_id)
        )
        
    return SafeStreamingResponse(
        local_file_generator(file_path, start, end, info_hash, debrid_provider),
        status_code=status_code,
        media_type=mime_type,
        headers=headers
    )


try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter, ImageStat
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    Image = ImageDraw = ImageFont = ImageOps = ImageFilter = ImageStat = None
    logger.warning("PIL / Pillow is not installed. Poster generation and image formatting will be disabled.")

_thumb_file_id_cache = {}
_thumb_download_semaphore = asyncio.Semaphore(3)
_thumb_resolve_semaphore = asyncio.Semaphore(2)
_active_thumb_downloads = set()
_failed_thumb_downloads = {}  # cache_key -> (timestamp, count)


def _is_black_image(image_path: str) -> bool:
    """Detect if an image is all black or too dark (< 16 avg brightness)."""
    if not HAS_PIL or not Image:
        return False
    try:
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            stat = ImageStat.Stat(im)
            avg_brightness = sum(stat.mean) / len(stat.mean)
            return avg_brightness < 16.0
    except Exception:
        return False


def generate_styled_placeholder_poster(title: str, size_str: str, output_path: str):
    """Generate a sleek, modern cinema-style placeholder poster with Pillow."""
    if not HAS_PIL or not Image:
        return
    width, height = 600, 900
    img = Image.new("RGB", (width, height), color=(15, 17, 26))
    draw = ImageDraw.Draw(img)

    # Top-to-bottom dark cinema gradient
    for y in range(height):
        ratio = y / height
        r = int(20 * (1 - ratio) + 10 * ratio)
        g = int(25 * (1 - ratio) + 12 * ratio)
        b = int(45 * (1 - ratio) + 22 * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Center glow
    for rad in range(160, 0, -6):
        alpha_factor = (160 - rad) / 160.0
        glow_color = (int(25 + 35 * alpha_factor), int(35 + 50 * alpha_factor), int(75 + 95 * alpha_factor))
        draw.ellipse([width // 2 - rad, height // 2 - 80 - rad, width // 2 + rad, height // 2 - 80 + rad], outline=glow_color)

    # Play button box
    cx, cy = width // 2, height // 2 - 80
    box_size = 48
    draw.rounded_rectangle(
        [cx - box_size, cy - box_size, cx + box_size, cy + box_size],
        radius=16, fill=(35, 45, 78), outline=(75, 95, 165), width=2
    )

    # Play triangle
    tri = [(cx - 10, cy - 18), (cx - 10, cy + 18), (cx + 18, cy)]
    draw.polygon(tri, fill=(230, 240, 255))

    # Fonts
    try:
        font_large = ImageFont.truetype("arial.ttf", 26)
        font_sub = ImageFont.truetype("arial.ttf", 16)
        font_badge = ImageFont.truetype("arialbd.ttf", 15)
    except Exception:
        font_large = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_badge = ImageFont.load_default()

    # Title
    clean_title = title if len(title) <= 34 else title[:31] + "..."
    draw.text((width // 2, height - 200), clean_title, font=font_large, fill=(255, 255, 255), anchor="mm")

    # Size Badge
    if size_str:
        draw.rounded_rectangle(
            [width // 2 - 75, height - 150, width // 2 + 75, height - 118],
            radius=8, fill=(25, 32, 52), outline=(65, 85, 135)
        )
        draw.text((width // 2, height - 134), f"📦 {size_str}", font=font_badge, fill=(140, 190, 255), anchor="mm")

    draw.text((width // 2, height - 60), "TELEGRAM MEDIA VAULT", font=font_sub, fill=(90, 105, 135), anchor="mm")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "JPEG", quality=90)


def _format_image_to_poster(input_path: str, output_path: str) -> bool:
    """Format any image (16:9 landscape, portrait, square) into a stunning 600x900 Cinema Poster."""
    try:
        with Image.open(input_path) as img:
            img = img.convert("RGB")
            w, h = img.size
            if w <= 0 or h <= 0:
                return False
            aspect = w / h
            poster_w, poster_h = 600, 900

            # If already near standard 2:3 portrait (0.58 - 0.75), direct fit
            if 0.58 <= aspect <= 0.75:
                result = ImageOps.fit(img, (poster_w, poster_h), method=Image.Resampling.LANCZOS)
            else:
                # 1. Create blurred backdrop
                bg = ImageOps.fit(img, (poster_w, poster_h), method=Image.Resampling.BILINEAR)
                bg = bg.filter(ImageFilter.GaussianBlur(28))
                dark_overlay = Image.new("RGB", (poster_w, poster_h), color=(10, 12, 20))
                bg = Image.blend(bg, dark_overlay, alpha=0.45)

                # 2. Scale foreground image maintaining original aspect ratio
                fg_w = poster_w
                fg_h = int(poster_w / aspect)
                if fg_h > poster_h:
                    fg_h = poster_h
                    fg_w = int(poster_h * aspect)

                fg = img.resize((fg_w, fg_h), Image.Resampling.LANCZOS)

                # 3. Paste foreground centered with border
                pos_x = (poster_w - fg_w) // 2
                pos_y = (poster_h - fg_h) // 2
                bg.paste(fg, (pos_x, pos_y))

                draw = ImageDraw.Draw(bg)
                draw.rectangle([pos_x, pos_y, pos_x + fg_w - 1, pos_y + fg_h - 1], outline=(55, 65, 90), width=1)
                result = bg

            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            result.save(output_path, "JPEG", quality=92)
            return True
    except Exception as e:
        logger.warning(f"Failed to format image to poster for {input_path}: {e}")
        return False


async def _extract_frame_with_ffmpeg(stream_url: str, output_path: str) -> bool:
    """Extract a crisp, bright frame snapshot directly from the video stream using FFmpeg."""
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        temp_frame = output_path + ".raw_frame.jpg"
        # Seek to real movie scenes (60s, 90s, 30s, 15s) to skip dark intros
        for seek in ["60", "90", "30", "15", "5"]:
            cmd = [
                "ffmpeg", "-y",
                "-ss", seek,
                "-i", stream_url,
                "-vframes", "1",
                "-q:v", "2",
                temp_frame
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            try:
                await asyncio.wait_for(proc.communicate(), timeout=8.0)
                if proc.returncode == 0 and os.path.exists(temp_frame) and os.path.getsize(temp_frame) > 500:
                    if not _is_black_image(temp_frame):
                        if _format_image_to_poster(temp_frame, output_path):
                            if os.path.exists(temp_frame):
                                os.remove(temp_frame)
                            logger.info(f"Successfully extracted bright video frame at {seek}s -> {output_path}")
                            return True
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
            finally:
                if os.path.exists(temp_frame):
                    try:
                        os.remove(temp_frame)
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"FFmpeg frame extraction failed for {stream_url}: {e}")
    return False


async def _process_thumbnail_task(chat_id: str, msg_id: int, thumb_path: str, thumb_file_id: Optional[str] = None):
    """Download Telegram thumbnail or extract real frame snapshot from video content."""
    cache_key = f"{chat_id}_{msg_id}"
    if cache_key in _active_thumb_downloads:
        return

    _active_thumb_downloads.add(cache_key)
    try:
        async with _thumb_download_semaphore:
            # 1. If Telegram has an embedded thumbnail, test if it is a real image (not black)
            if thumb_file_id:
                temp_raw = thumb_path + ".raw.jpg"
                try:
                    logger.info(f"Downloading Telegram embedded thumbnail for msg {msg_id} in {chat_id}...")
                    await tg_client_manager.client.download_media(thumb_file_id, file_name=temp_raw)
                    if os.path.exists(temp_raw) and os.path.getsize(temp_raw) > 50:
                        if not _is_black_image(temp_raw):
                            if _format_image_to_poster(temp_raw, thumb_path):
                                if os.path.exists(temp_raw):
                                    os.remove(temp_raw)
                                _failed_thumb_downloads.pop(cache_key, None)
                                return
                        else:
                            logger.info(f"Embedded Telegram thumb for msg {msg_id} is pitch black. Extracting real frame via FFmpeg...")
                except Exception as de:
                    logger.warning(f"Failed to download embedded thumbnail for {cache_key}: {de}")
                finally:
                    if os.path.exists(temp_raw):
                        try:
                            os.remove(temp_raw)
                        except Exception:
                            pass

            # 2. Extract snapshot from video content via local HTTP Range stream
            try:
                chat_id_val = int(chat_id) if str(chat_id).startswith("-") or str(chat_id).isdigit() else chat_id
                msg = await tg_client_manager.get_message(msg_id, chat_id=chat_id_val)
            except Exception:
                msg = None

            if msg:
                media = msg.video or msg.document
                if media:
                    # Check if message has thumbs that weren't in memory cache
                    thumb = getattr(media, "thumb", None)
                    thumbs = getattr(media, "thumbs", None)
                    resolved_fid = getattr(thumb, "file_id", None) if thumb else (thumbs[-1].file_id if thumbs else None)
                    if resolved_fid and not thumb_file_id:
                        temp_raw = thumb_path + ".raw.jpg"
                        try:
                            logger.info(f"Downloading resolved Telegram thumbnail for msg {msg_id} in {chat_id}...")
                            await tg_client_manager.client.download_media(resolved_fid, file_name=temp_raw)
                            if os.path.exists(temp_raw) and os.path.getsize(temp_raw) > 50:
                                if not _is_black_image(temp_raw):
                                    if _format_image_to_poster(temp_raw, thumb_path):
                                        if os.path.exists(temp_raw):
                                            os.remove(temp_raw)
                                        _failed_thumb_downloads.pop(cache_key, None)
                                        return
                        except Exception:
                            pass
                        finally:
                            if os.path.exists(temp_raw):
                                try:
                                    os.remove(temp_raw)
                                except Exception:
                                    pass

                    filename = getattr(media, "file_name", None) or msg.caption or f"video_{msg_id}.mp4"
                    file_size = getattr(media, "file_size", 0)
                    stream_url = f"http://127.0.0.1:{Config.PORT}/stream/file/{chat_id}/{msg_id}/{urllib.parse.quote(filename)}"

                    logger.info(f"Extracting bright video frame snapshot for msg {msg_id} ({filename})...")
                    success = await _extract_frame_with_ffmpeg(stream_url, thumb_path)
                    if success:
                        _failed_thumb_downloads.pop(cache_key, None)
                        return

                    # 3. Fallback: generate high-res stylized poster
                    generate_styled_placeholder_poster(filename, format_size(file_size), thumb_path)
                    _failed_thumb_downloads.pop(cache_key, None)
                    return

            # Default generic poster if message resolution failed
            generate_styled_placeholder_poster(f"Telegram File {msg_id}", "", thumb_path)

    except Exception as e:
        logger.error(f"Thumbnail processing failed for {cache_key}: {e}")
        now = time.time()
        _, count = _failed_thumb_downloads.get(cache_key, (0, 0))
        _failed_thumb_downloads[cache_key] = (now, count + 1)
    finally:
        _active_thumb_downloads.discard(cache_key)


def get_message_thumbnail_url(msg, logo_url: str) -> str:
    """Generate the thumbnail URL for any video/document message in Telegram."""
    if not msg:
        return logo_url
    media = msg.video or msg.document or msg.photo
    if media:
        chat_id = msg.chat.id
        msg_id = msg.id
        thumb = getattr(media, "thumb", None)
        thumbs = getattr(media, "thumbs", None)
        fid = getattr(thumb, "file_id", None) if thumb else (thumbs[-1].file_id if thumbs else None)
        if fid:
            _thumb_file_id_cache[f"{chat_id}_{msg_id}"] = fid

        query = f"?api_key={Config.API_KEY}" if Config.API_KEY else ""
        return f"{Config.ADDON_URL}/thumbnail/{chat_id}/{msg_id}.jpg{query}"
    return logo_url


@app.get("/thumbnail/{chat_id}/{msg_id}.jpg")
async def get_message_thumbnail(
    chat_id: str,
    msg_id: int,
    request: Request,
    api_key: str = ""
):
    if Config.API_KEY:
        actual_key = api_key or request.query_params.get("api_key", "")
        if actual_key != Config.API_KEY:
            raise HTTPException(status_code=403, detail="Unauthorized")

    temp_dir = os.path.join("temp_cache", "thumbs")
    os.makedirs(temp_dir, exist_ok=True)

    thumb_path = os.path.join(temp_dir, f"{chat_id}_{msg_id}.jpg")
    default_logo = "stremio_telegram_logo.png"

    # 1. Serve immediately if cached on disk
    if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 500:
        return FileResponse(
            thumb_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"}
        )

    cache_key = f"{chat_id}_{msg_id}"
    thumb_file_id = _thumb_file_id_cache.get(cache_key)

    # 2. Synchronously await thumbnail processing for up to 8.0s so the very first request gets the real image!
    try:
        await asyncio.wait_for(
            _process_thumbnail_task(chat_id, msg_id, thumb_path, thumb_file_id),
            timeout=8.0
        )
    except Exception:
        pass

    if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 500:
        return FileResponse(
            thumb_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"}
        )

    # 3. Fallback placeholder with no-cache header so Stremio re-requests immediately
    if os.path.exists(default_logo):
        return FileResponse(
            default_logo,
            media_type="image/png",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate, max-age=0"}
        )

    raise HTTPException(status_code=404, detail="Thumbnail not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("addon:app", host="0.0.0.0", port=Config.PORT, reload=True)
