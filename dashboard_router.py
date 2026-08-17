import logging
import asyncio
import time
import os
import socket
import urllib.parse
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse
import httpx

from config import Config
from tg_client import tg_client_manager

logger = logging.getLogger("dashboard")
dashboard_router = APIRouter()

SERVER_START_TIME = time.time()

# In-memory log buffer for dashboard log viewer
class LogBufferHandler(logging.Handler):
    def __init__(self, capacity: int = 150):
        super().__init__()
        self.capacity = capacity
        self.buffer: List[Dict[str, Any]] = []

    def emit(self, record):
        try:
            msg = self.format(record)
            entry = {
                "time": time.strftime("%H:%M:%S", time.localtime(record.created)),
                "level": record.levelname,
                "name": record.name,
                "message": msg
            }
            self.buffer.append(entry)
            if len(self.buffer) > self.capacity:
                self.buffer.pop(0)
        except Exception:
            pass

log_buffer_handler = LogBufferHandler(200)
log_buffer_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] (%(name)s) - %(message)s", "%H:%M:%S"))
logging.getLogger().addHandler(log_buffer_handler)


def get_lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


@dashboard_router.get("/api/system/status")
async def api_system_status(request: Request):
    uptime_sec = int(time.time() - SERVER_START_TIME)
    hours, remainder = divmod(uptime_sec, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours}h {minutes}m {seconds}s"

    lan_ip = get_lan_ip()
    port = Config.PORT
    base_url = str(request.base_url).rstrip("/")

    tg_connected = False
    tg_user = None
    try:
        if tg_client_manager.client and tg_client_manager.client.is_connected:
            tg_connected = True
            if tg_client_manager.me:
                tg_user = getattr(tg_client_manager.me, "first_name", "") or getattr(tg_client_manager.me, "username", "Connected")
    except Exception:
        pass

    # Disk cache stats
    moviesdrive_cache_count = 0
    try:
        from moviesdrive_catalog import MOVIESDRIVE_CACHE
        moviesdrive_cache_count = len(MOVIESDRIVE_CACHE)
    except Exception:
        pass

    return {
        "status": "online",
        "uptime": uptime_str,
        "uptime_seconds": uptime_sec,
        "port": port,
        "lan_ip": lan_ip,
        "base_url": base_url,
        "configured_url": Config.ADDON_URL,
        "telegram": {
            "connected": tg_connected,
            "user": tg_user,
            "channel_id": Config.TELEGRAM_CHANNEL_ID or "Chưa cấu hình",
            "has_session": bool(Config.USER_SESSION_STRING),
            "has_bot_token": bool(Config.BOT_TOKEN)
        },
        "services": {
            "real_debrid": bool(Config.REAL_DEBRID_API_KEY),
            "torbox": bool(Config.TORBOX_API_KEY),
            "qbittorrent": bool(Config.QBITTORRENT_URL),
            "gemini_ai": bool(Config.GEMINI_API_KEY),
            "auto_upload": Config.AUTO_UPLOAD_TO_TELEGRAM,
            "auto_vietsub": Config.AUTO_VIET_SUB
        },
        "stats": {
            "moviesdrive_cache_entries": moviesdrive_cache_count,
            "log_entries": len(log_buffer_handler.buffer)
        }
    }


@dashboard_router.get("/api/system/addons")
async def api_system_addons(request: Request):
    lan_ip = get_lan_ip()
    port = Config.PORT
    base_url = str(request.base_url).rstrip("/")
    api_key_suffix = f"?api_key={urllib.parse.quote(Config.API_KEY)}" if Config.API_KEY else ""

    addons = [
        {
            "id": "telegram_debrid",
            "name": "Telegram Media Vault & Debrid",
            "tag": "Kho Phim Cá Nhân",
            "category": "Private & Torrents",
            "icon": "fa-telegram",
            "badge": "Core Engine",
            "badge_color": "blue",
            "description": "Phát phim trực tiếp từ kênh Telegram riêng tư, Range Requests tua nhanh tức thì, Debrid CDN stream & tải torrent qBittorrent.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/manifest.json{api_key_suffix}",
                "lan": f"http://{lan_ip}:{port}/manifest.json{api_key_suffix}",
                "public": f"{base_url}/manifest.json{api_key_suffix}"
            },
            "routes": ["/manifest.json", "/stream", "/meta", "/catalog"]
        },
        {
            "id": "nguonc",
            "name": "NguonC Cinema",
            "tag": "Kho Phim Tổng Hợp",
            "category": "VietSub & Thuyết Minh",
            "icon": "fa-film",
            "badge": "22 Thể Loại",
            "badge_color": "emerald",
            "description": "Tích hợp toàn bộ API NguonC với Phim Lẻ, Phim Bộ, TV Shows, Hoạt Hình. Tự động giải mã HLS .m3u8 proxy.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/nguonc/manifest.json",
                "lan": f"http://{lan_ip}:{port}/nguonc/manifest.json",
                "public": f"{base_url}/nguonc/manifest.json"
            },
            "routes": ["/nguonc/manifest.json", "/nguonc/catalog", "/nguonc/stream"]
        },
        {
            "id": "vsmov",
            "name": "VSMov Cinema",
            "tag": "Phim Chiếu Rạp",
            "category": "Full HD / 4K Vietsub",
            "icon": "fa-play-circle",
            "badge": "Tốc Độ Cao",
            "badge_color": "purple",
            "description": "Kho phim Châu Á và Âu Mỹ vietsub/thuyết minh tốc độ cao, chất lượng sắc nét Full HD / 4K không quảng cáo.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/vsmov/manifest.json",
                "lan": f"http://{lan_ip}:{port}/vsmov/manifest.json",
                "public": f"{base_url}/vsmov/manifest.json"
            },
            "routes": ["/vsmov/manifest.json", "/vsmov/catalog", "/vsmov/stream"]
        },
        {
            "id": "hhpanda",
            "name": "HHPanda 3D Anime",
            "tag": "Hoạt Hình 3D Trung Quốc",
            "category": "HH3D 4K VietSub",
            "icon": "fa-dragon",
            "badge": "Tu Tiên / Kiếm Hiệp",
            "badge_color": "cyan",
            "description": "Kho phim Hoạt Hình 3D Trung Quốc siêu nét 4K/1080P: Tiên Nghịch, Đấu Phá Thương Khung, Thế Giới Hoàn Mỹ, Phàm Nhân Tu Tiên...",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/hhpanda/manifest.json",
                "lan": f"http://{lan_ip}:{port}/hhpanda/manifest.json",
                "public": f"{base_url}/hhpanda/manifest.json"
            },
            "routes": ["/hhpanda/manifest.json", "/hhpanda/catalog", "/hhpanda/stream"]
        },
        {
            "id": "moviesdrive",
            "name": "MoviesDrive Cinema",
            "tag": "Hollywood / Bollywood",
            "category": "4K UHD & Dual Audio",
            "icon": "fa-clapperboard",
            "badge": "4K HDR",
            "badge_color": "amber",
            "description": "Phim bom tấn 4K UHD, 1080p từ MoviesDrive. Tự động giải mã link HubCloud, GDFlix, DoodStream và khớp mã IMDb khi duyệt phim.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/moviesdrive/manifest.json",
                "lan": f"http://{lan_ip}:{port}/moviesdrive/manifest.json",
                "public": f"{base_url}/moviesdrive/manifest.json"
            },
            "routes": ["/moviesdrive/manifest.json", "/moviesdrive/catalog", "/moviesdrive/stream"]
        },
        {
            "id": "hdhub4u",
            "name": "HDHub4u Cinema",
            "tag": "Hollywood & Web Series",
            "category": "Fast 10Gbps CDN",
            "icon": "fa-bolt",
            "badge": "Cloudflare R2",
            "badge_color": "rose",
            "description": "Kho phim Hollywood / Bollywood Dual Audio chất lượng cao, hạ tầng CDN Cloudflare R2 / FastDL 10Gbps phát mượt mà.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/hdhub4u/manifest.json",
                "lan": f"http://{lan_ip}:{port}/hdhub4u/manifest.json",
                "public": f"{base_url}/hdhub4u/manifest.json"
            },
            "routes": ["/hdhub4u/manifest.json", "/hdhub4u/catalog", "/hdhub4u/stream"]
        },
        {
            "id": "topxx",
            "name": "TopXX Cinema",
            "tag": "Kho Phim 18+",
            "category": "Adult Streaming",
            "icon": "fa-heart",
            "badge": "18+ Only",
            "badge_color": "red",
            "description": "Kho phim giải trí 18+ chất lượng cao phân loại theo thể loại, diễn viên và hỗ trợ phát trực tiếp trên Stremio.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/topxx/manifest.json",
                "lan": f"http://{lan_ip}:{port}/topxx/manifest.json",
                "public": f"{base_url}/topxx/manifest.json"
            },
            "routes": ["/topxx/manifest.json", "/topxx/catalog", "/topxx/stream"]
        }
    ]
    return {"addons": addons}


@dashboard_router.get("/api/system/logs")
async def api_system_logs():
    return {"logs": log_buffer_handler.buffer[-100:]}


@dashboard_router.post("/api/cache/clear")
async def api_clear_cache():
    cleared = []
    try:
        from addon import DEBRID_STREAM_URL_CACHE
        count = len(DEBRID_STREAM_URL_CACHE)
        DEBRID_STREAM_URL_CACHE.clear()
        cleared.append(f"Debrid Stream Cache ({count} entries)")
    except Exception:
        pass

    try:
        from moviesdrive_catalog import MOVIESDRIVE_CACHE
        m_count = len(MOVIESDRIVE_CACHE)
        MOVIESDRIVE_CACHE.clear()
        cleared.append(f"MoviesDrive Catalog Cache ({m_count} entries)")
    except Exception:
        pass

    logger.info(f"Admin Dashboard cleared caches: {', '.join(cleared)}")
    return {"success": True, "message": "Đã xóa toàn bộ bộ nhớ đệm thành công!", "cleared": cleared}


@dashboard_router.get("/api/search")
async def api_universal_search(q: str = Query(..., min_length=1), source: Optional[str] = None):
    query = q.strip()
    results = []

    async def search_nguonc():
        items = []
        try:
            url = f"https://phim.nguonc.com/api/films/search?keyword={urllib.parse.quote(query)}"
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    items_list = data.get("items", []) or data.get("data", {}).get("items", [])
                    for item in items_list[:12]:
                        slug = item.get("slug", "")
                        items.append({
                            "id": f"nguonc:{slug}",
                            "title": item.get("name", "Unknown"),
                            "original_title": item.get("original_name", ""),
                            "source": "NguonC",
                            "source_id": "nguonc",
                            "poster": item.get("poster_url", "") or item.get("thumb_url", ""),
                            "year": item.get("year", ""),
                            "quality": item.get("quality", "HD"),
                            "type": "movie" if item.get("type") == "single" else "series",
                            "detail_url": f"/api/media/details?source=nguonc&id={slug}"
                        })
        except Exception as e:
            logger.warning(f"Dashboard search NguonC error: {e}")
        return items

    async def search_vsmov():
        items = []
        try:
            url = f"https://vsmov.com/api/search?q={urllib.parse.quote(query)}"
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    for item in data.get("results", [])[:10]:
                        items.append({
                            "id": f"vsmov:{item.get('id', '')}",
                            "title": item.get("title", ""),
                            "original_title": item.get("original_title", ""),
                            "source": "VSMov",
                            "source_id": "vsmov",
                            "poster": item.get("poster", ""),
                            "year": item.get("year", ""),
                            "quality": "Full HD",
                            "type": "series" if item.get("is_series") else "movie",
                            "detail_url": f"/api/media/details?source=vsmov&id={item.get('id')}"
                        })
        except Exception:
            pass
        return items

    async def search_hhpanda():
        items = []
        try:
            url = f"https://hhpanda.st/tim-kiem?q={urllib.parse.quote(query)}"
            async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://hhpanda.st/"}) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    import re
                    pattern = r'<a\s+href="https://hhpanda\.st/([^"]+)"[^>]*title="([^"]+)"[^>]*>.*?<img[^>]+(?:data-src|src)="([^"]+)"'
                    matches = re.findall(pattern, res.text, re.DOTALL)
                    for match in matches[:8]:
                        slug, title, poster = match
                        if not slug.startswith("tim-kiem") and not slug.startswith("the-loai"):
                            items.append({
                                "id": f"hhpanda:{slug}",
                                "title": title,
                                "original_title": "HH3D",
                                "source": "HHPanda 3D",
                                "source_id": "hhpanda",
                                "poster": poster,
                                "year": "2024-2026",
                                "quality": "4K/1080P",
                                "type": "series",
                                "detail_url": f"/api/media/details?source=hhpanda&id={slug}"
                            })
        except Exception:
            pass
        return items

    tasks = []
    if not source or source == "all" or source == "nguonc":
        tasks.append(search_nguonc())
    if not source or source == "all" or source == "vsmov":
        tasks.append(search_vsmov())
    if not source or source == "all" or source == "hhpanda":
        tasks.append(search_hhpanda())

    results_lists = await asyncio.gather(*tasks, return_exceptions=True)
    for res_list in results_lists:
        if isinstance(res_list, list):
            results.extend(res_list)

    return {"query": query, "total": len(results), "results": results}


@dashboard_router.get("/api/media/details")
async def api_media_details(source: str, id: str):
    if source == "nguonc":
        try:
            url = f"https://phim.nguonc.com/api/film/{id}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    movie = data.get("movie", {}) or data.get("data", {}).get("item", {})
                    episodes = []
                    for ep_server in movie.get("episodes", []):
                        server_name = ep_server.get("server_name", "VIP Server")
                        for ep in ep_server.get("items", []):
                            episodes.append({
                                "name": ep.get("name", ""),
                                "slug": ep.get("slug", ""),
                                "server": server_name,
                                "embed": ep.get("embed", ""),
                                "m3u8": ep.get("m3u8", "")
                            })
                    return {
                        "title": movie.get("name", ""),
                        "original_title": movie.get("original_name", ""),
                        "description": movie.get("description", "") or movie.get("content", ""),
                        "poster": movie.get("poster_url", "") or movie.get("thumb_url", ""),
                        "year": movie.get("year", ""),
                        "episodes": episodes
                    }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=404, detail="Source detail handler not implemented")


@dashboard_router.get("/dashboard", response_class=HTMLResponse)
@dashboard_router.get("/admin", response_class=HTMLResponse)
async def dashboard_ui(request: Request):
    html = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ Trung Tâm Quản Lý Addon & Nguồn Phim</title>
    <meta name="description" content="Dashboard quản lý và cài đặt các nguồn phim Stremio: Telegram Vault, NguonC, VSMov, HHPanda, MoviesDrive, HDHub4u, TopXX.">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Outfit:wght@400;500;600;700;800&family=Inter:wght@300;400;500;600&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <style>
        :root {
            --bg-body: #09090b;
            --bg-sidebar: #111115;
            --bg-card: #18181b;
            --bg-card-hover: #222226;
            --border-color: #27272a;
            --border-accent: rgba(99, 102, 241, 0.3);
            --primary: #6366f1;
            --primary-hover: #4f46e5;
            --primary-light: rgba(99, 102, 241, 0.15);
            --accent: #8b5cf6;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --cyan: #06b6d4;
            --text-main: #f4f4f5;
            --text-muted: #a1a1aa;
            --text-dim: #71717a;
            --radius-lg: 16px;
            --radius-md: 12px;
            --radius-sm: 8px;
            --shadow-glow: 0 0 25px rgba(99, 102, 241, 0.15);
            --font-heading: 'Outfit', sans-serif;
            --font-body: 'Plus Jakarta Sans', sans-serif;
            --font-mono: 'Fira Code', monospace;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: var(--font-body);
            background-color: var(--bg-body);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            overflow-x: hidden;
        }

        /* Layout */
        .app-container {
            display: flex;
            width: 100vw;
            height: 100vh;
            overflow: hidden;
        }

        /* Sidebar */
        .sidebar {
            width: 280px;
            background: var(--bg-sidebar);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            flex-shrink: 0;
            z-index: 20;
            transition: transform 0.3s ease;
        }

        .sidebar-brand {
            padding: 24px 20px;
            display: flex;
            align-items: center;
            gap: 12px;
            border-bottom: 1px solid var(--border-color);
        }

        .brand-icon {
            width: 40px;
            height: 40px;
            border-radius: var(--radius-md);
            background: linear-gradient(135deg, var(--primary), var(--accent));
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            color: #fff;
            box-shadow: var(--shadow-glow);
        }

        .brand-text h1 {
            font-family: var(--font-heading);
            font-size: 18px;
            font-weight: 700;
            color: #fff;
            letter-spacing: -0.3px;
        }

        .brand-text p {
            font-size: 12px;
            color: var(--text-dim);
            font-weight: 500;
        }

        .nav-menu {
            padding: 16px 12px;
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 6px;
            flex: 1;
            overflow-y: auto;
        }

        .nav-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 16px;
            border-radius: var(--radius-md);
            color: var(--text-muted);
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            text-decoration: none;
        }

        .nav-item i {
            font-size: 16px;
            width: 20px;
            text-align: center;
        }

        .nav-item:hover {
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-main);
        }

        .nav-item.active {
            background: var(--primary-light);
            color: var(--primary);
            border: 1px solid var(--border-accent);
        }

        .nav-badge {
            margin-left: auto;
            background: var(--primary);
            color: #fff;
            font-size: 11px;
            font-weight: 700;
            padding: 2px 7px;
            border-radius: 20px;
        }

        .sidebar-footer {
            padding: 16px 20px;
            border-top: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            font-weight: 600;
            color: var(--success);
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--success);
            box-shadow: 0 0 8px var(--success);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.4; transform: scale(0.85); }
        }

        /* Main Content */
        .main-wrapper {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            background: var(--bg-body);
        }

        .top-navbar {
            height: 70px;
            border-bottom: 1px solid var(--border-color);
            background: rgba(17, 17, 21, 0.8);
            backdrop-filter: blur(12px);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 32px;
            z-index: 10;
        }

        .top-title h2 {
            font-family: var(--font-heading);
            font-size: 20px;
            font-weight: 700;
            color: #fff;
        }

        .top-actions {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .btn {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 9px 16px;
            border-radius: var(--radius-md);
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            border: 1px solid transparent;
            text-decoration: none;
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--primary), var(--accent));
            color: #fff;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25);
        }

        .btn-primary:hover {
            opacity: 0.92;
            transform: translateY(-1px);
        }

        .btn-secondary {
            background: var(--bg-card);
            border-color: var(--border-color);
            color: var(--text-main);
        }

        .btn-secondary:hover {
            background: var(--bg-card-hover);
            border-color: #3f3f46;
        }

        .btn-danger {
            background: rgba(239, 68, 68, 0.15);
            border-color: rgba(239, 68, 68, 0.3);
            color: var(--danger);
        }

        .btn-danger:hover {
            background: var(--danger);
            color: #fff;
        }

        .btn-sm {
            padding: 6px 12px;
            font-size: 12px;
        }

        /* Content Area */
        .content-scroll {
            flex: 1;
            overflow-y: auto;
            padding: 32px;
        }

        .tab-pane {
            display: none;
            flex-direction: column;
            gap: 28px;
            animation: fadeIn 0.25s ease forwards;
        }

        .tab-pane.active {
            display: flex;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Stats Cards */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 20px;
        }

        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            padding: 20px;
            display: flex;
            align-items: center;
            gap: 16px;
            position: relative;
            overflow: hidden;
        }

        .stat-card::after {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
            background: var(--card-color, var(--primary));
        }

        .stat-icon-wrapper {
            width: 48px;
            height: 48px;
            border-radius: var(--radius-md);
            background: rgba(255, 255, 255, 0.05);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            color: var(--card-color, var(--primary));
        }

        .stat-info h4 {
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-dim);
            font-weight: 600;
            margin-bottom: 4px;
        }

        .stat-info p {
            font-family: var(--font-heading);
            font-size: 22px;
            font-weight: 700;
            color: #fff;
        }

        /* Addon Cards Grid */
        .addons-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
            gap: 24px;
        }

        .addon-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 18px;
            transition: all 0.25s ease;
            position: relative;
        }

        .addon-card:hover {
            border-color: var(--border-accent);
            transform: translateY(-3px);
            box-shadow: var(--shadow-glow);
        }

        .addon-header {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 12px;
        }

        .addon-title-group {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .addon-icon {
            width: 44px;
            height: 44px;
            border-radius: var(--radius-md);
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            color: var(--addon-theme, var(--primary));
        }

        .addon-title-group h3 {
            font-family: var(--font-heading);
            font-size: 17px;
            font-weight: 700;
            color: #fff;
        }

        .addon-title-group span {
            font-size: 12px;
            color: var(--text-dim);
            font-weight: 500;
        }

        .badge-tag {
            font-size: 11px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 20px;
            background: rgba(99, 102, 241, 0.12);
            color: var(--primary);
            border: 1px solid rgba(99, 102, 241, 0.3);
            white-space: nowrap;
        }

        .addon-desc {
            font-size: 13px;
            color: var(--text-muted);
            line-height: 1.5;
            flex: 1;
        }

        .manifest-selector {
            display: flex;
            flex-direction: column;
            gap: 8px;
            background: rgba(0, 0, 0, 0.25);
            padding: 12px;
            border-radius: var(--radius-md);
            border: 1px solid var(--border-color);
        }

        .manifest-url-row {
            display: flex;
            align-items: center;
            gap: 8px;
            background: var(--bg-body);
            border: 1px solid #3f3f46;
            border-radius: var(--radius-sm);
            padding: 6px 10px;
        }

        .manifest-url-input {
            flex: 1;
            background: transparent;
            border: none;
            color: var(--cyan);
            font-family: var(--font-mono);
            font-size: 11px;
            outline: none;
        }

        .addon-actions {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-top: 4px;
        }

        /* Search Explorer */
        .search-hero {
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.12), rgba(139, 92, 246, 0.08));
            border: 1px solid var(--border-accent);
            border-radius: var(--radius-lg);
            padding: 32px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .search-hero h3 {
            font-family: var(--font-heading);
            font-size: 24px;
            font-weight: 700;
            color: #fff;
        }

        .search-bar-group {
            display: flex;
            gap: 12px;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            padding: 6px;
        }

        .search-input {
            flex: 1;
            background: transparent;
            border: none;
            padding: 10px 16px;
            font-size: 15px;
            color: #fff;
            outline: none;
        }

        .source-select {
            background: var(--bg-body);
            border: 1px solid var(--border-color);
            color: var(--text-main);
            padding: 0 16px;
            border-radius: var(--radius-sm);
            outline: none;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
        }

        .media-results-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 20px;
        }

        .media-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            overflow: hidden;
            display: flex;
            flex-direction: column;
            transition: all 0.2s ease;
            cursor: pointer;
        }

        .media-card:hover {
            border-color: var(--primary);
            transform: translateY(-4px);
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
        }

        .media-poster-box {
            position: relative;
            width: 100%;
            padding-top: 140%;
            background: #27272a;
            overflow: hidden;
        }

        .media-poster-img {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .media-badge-source {
            position: absolute;
            top: 8px;
            left: 8px;
            background: rgba(0, 0, 0, 0.75);
            backdrop-filter: blur(4px);
            font-size: 10px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 6px;
            color: #fff;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }

        .media-badge-quality {
            position: absolute;
            bottom: 8px;
            right: 8px;
            background: var(--primary);
            font-size: 10px;
            font-weight: 700;
            padding: 2px 6px;
            border-radius: 4px;
            color: #fff;
        }

        .media-info {
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .media-title {
            font-size: 14px;
            font-weight: 700;
            color: #fff;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .media-sub {
            font-size: 12px;
            color: var(--text-dim);
        }

        /* Logs Console */
        .log-console {
            background: #000;
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            padding: 16px;
            font-family: var(--font-mono);
            font-size: 12px;
            color: #d4d4d8;
            height: 480px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .log-line {
            display: flex;
            gap: 12px;
            line-height: 1.4;
        }

        .log-time { color: var(--text-dim); flex-shrink: 0; }
        .log-lvl-INFO { color: var(--cyan); }
        .log-lvl-WARNING { color: var(--warning); }
        .log-lvl-ERROR { color: var(--danger); }
        .log-msg { color: #f4f4f5; word-break: break-all; }

        /* Modal Player */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(0, 0, 0, 0.85);
            backdrop-filter: blur(8px);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 100;
            padding: 20px;
        }

        .modal-overlay.active {
            display: flex;
        }

        .modal-box {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            width: 100%;
            max-width: 900px;
            max-height: 90vh;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.7);
        }

        .modal-header {
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .modal-body {
            padding: 20px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .video-container {
            width: 100%;
            background: #000;
            border-radius: var(--radius-md);
            overflow: hidden;
            position: relative;
            padding-top: 56.25%;
        }

        .video-player {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
        }

        .episode-chips {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            max-height: 140px;
            overflow-y: auto;
        }

        .ep-chip {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            color: var(--text-main);
            padding: 6px 12px;
            border-radius: var(--radius-sm);
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .ep-chip:hover, .ep-chip.active {
            background: var(--primary);
            border-color: var(--primary);
            color: #fff;
        }

        /* Toast notification */
        .toast-container {
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 200;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .toast {
            background: var(--bg-card);
            border: 1px solid var(--border-accent);
            padding: 12px 18px;
            border-radius: var(--radius-md);
            font-size: 13px;
            font-weight: 600;
            color: #fff;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            gap: 10px;
            animation: slideUp 0.25s ease;
        }

        @keyframes slideUp {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @media (max-width: 860px) {
            .sidebar {
                position: fixed;
                left: -280px;
                height: 100vh;
            }
            .sidebar.mobile-open {
                transform: translateX(280px);
            }
            .content-scroll {
                padding: 16px;
            }
        }
    </style>
</head>
<body>
    <div class="app-container">
        <!-- Sidebar -->
        <aside class="sidebar" id="sidebar">
            <div class="sidebar-brand">
                <div class="brand-icon">
                    <i class="fa-solid fa-layer-group"></i>
                </div>
                <div class="brand-text">
                    <h1>Addon Studio</h1>
                    <p>Cinema & Media Hub</p>
                </div>
            </div>

            <ul class="nav-menu">
                <li>
                    <a class="nav-item active" onclick="switchTab('dashboard')">
                        <i class="fa-solid fa-chart-pie"></i>
                        <span>Tổng Quan</span>
                    </a>
                </li>
                <li>
                    <a class="nav-item" onclick="switchTab('addons')">
                        <i class="fa-solid fa-puzzle-piece"></i>
                        <span>Quản Lý Nguồn</span>
                        <span class="nav-badge">7 Nguồn</span>
                    </a>
                </li>
                <li>
                    <a class="nav-item" onclick="switchTab('explorer')">
                        <i class="fa-solid fa-magnifying-glass"></i>
                        <span>Tìm Phim & Player</span>
                    </a>
                </li>
                <li>
                    <a class="nav-item" onclick="switchTab('services')">
                        <i class="fa-solid fa-sliders"></i>
                        <span>Cấu Hình & Dịch Vụ</span>
                    </a>
                </li>
                <li>
                    <a class="nav-item" onclick="switchTab('logs')">
                        <i class="fa-solid fa-terminal"></i>
                        <span>Nhật Ký & Cache</span>
                    </a>
                </li>
            </ul>

            <div class="sidebar-footer">
                <div class="status-pill">
                    <span class="status-dot"></span>
                    <span id="sidebarStatusText">Máy chủ Online</span>
                </div>
                <a href="/" class="btn btn-secondary btn-sm" title="Về trang gốc">
                    <i class="fa-solid fa-house"></i>
                </a>
            </div>
        </aside>

        <!-- Main Content -->
        <main class="main-wrapper">
            <header class="top-navbar">
                <div class="top-title">
                    <h2 id="pageTitle">📊 Bảng Điều Khiển Tổng Quan</h2>
                </div>
                <div class="top-actions">
                    <button class="btn btn-secondary btn-sm" onclick="fetchSystemStatus()">
                        <i class="fa-solid fa-rotate"></i> Làm mới
                    </button>
                    <a href="https://web.stremio.com" target="_blank" class="btn btn-primary btn-sm">
                        <i class="fa-solid fa-tv"></i> Mở Stremio Web
                    </a>
                </div>
            </header>

            <div class="content-scroll">
                <!-- TAB 1: Dashboard -->
                <div class="tab-pane active" id="tab-dashboard">
                    <div class="stats-grid">
                        <div class="stat-card" style="--card-color: var(--primary);">
                            <div class="stat-icon-wrapper">
                                <i class="fa-solid fa-clock"></i>
                            </div>
                            <div class="stat-info">
                                <h4>Thời Gian Chạy</h4>
                                <p id="statUptime">Đang tải...</p>
                            </div>
                        </div>

                        <div class="stat-card" style="--card-color: var(--cyan);">
                            <div class="stat-icon-wrapper">
                                <i class="fa-brands fa-telegram"></i>
                            </div>
                            <div class="stat-info">
                                <h4>Telegram Client</h4>
                                <p id="statTelegram">Đang kiểm tra...</p>
                            </div>
                        </div>

                        <div class="stat-card" style="--card-color: var(--success);">
                            <div class="stat-icon-wrapper">
                                <i class="fa-solid fa-network-wired"></i>
                            </div>
                            <div class="stat-info">
                                <h4>Địa Chỉ LAN</h4>
                                <p id="statLanIp">127.0.0.1</p>
                            </div>
                        </div>

                        <div class="stat-card" style="--card-color: var(--warning);">
                            <div class="stat-icon-wrapper">
                                <i class="fa-solid fa-database"></i>
                            </div>
                            <div class="stat-info">
                                <h4>Cache Đã Lưu</h4>
                                <p id="statCacheEntries">0 mục</p>
                            </div>
                        </div>
                    </div>

                    <!-- Quick Addon Grid in Overview -->
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 10px;">
                        <h3 style="font-family: var(--font-heading); font-size: 18px; font-weight: 700;">📦 Danh Sách Nguồn Phim Sẵn Sàng</h3>
                        <button class="btn btn-secondary btn-sm" onclick="switchTab('addons')">Xem chi tiết tất cả &rarr;</button>
                    </div>

                    <div class="addons-grid" id="overviewAddonsGrid">
                        <!-- Loaded dynamically -->
                    </div>
                </div>

                <!-- TAB 2: Addons Hub -->
                <div class="tab-pane" id="tab-addons">
                    <div style="display: flex; align-items: center; justify-content: space-between;">
                        <div>
                            <h3 style="font-family: var(--font-heading); font-size: 20px; font-weight: 700; color: #fff;">🧩 Trung Tâm Cài Đặt Addon</h3>
                            <p style="font-size: 13px; color: var(--text-dim); margin-top: 4px;">Cài đặt 1-chạm hoặc sao chép Manifest URL tương thích với PC, Android TV và Web.</p>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <label style="font-size: 12px; font-weight: 600; color: var(--text-muted);">Môi trường URL:</label>
                            <select id="envUrlSelector" class="source-select" style="height: 36px;" onchange="renderAddonCards()">
                                <option value="lan">Mạng LAN (Android TV / Điện thoại)</option>
                                <option value="local">Máy tính cục bộ (127.0.0.1)</option>
                                <option value="public">Tên miền Host hiện tại</option>
                            </select>
                        </div>
                    </div>

                    <div class="addons-grid" id="fullAddonsGrid">
                        <!-- Loaded dynamically -->
                    </div>
                </div>

                <!-- TAB 3: Explorer & Player -->
                <div class="tab-pane" id="tab-explorer">
                    <div class="search-hero">
                        <h3>🔍 Tra Cứu Phim & Xem Thử Trực Tiếp</h3>
                        <div class="search-bar-group">
                            <input type="text" id="searchInput" class="search-input" placeholder="Nhập tên phim cần tìm (ví dụ: Tiên Nghịch, Spider-man, Avatar, Thợ Săn...)" onkeydown="if(event.key==='Enter') executeSearch()">
                            <select id="searchSourceSelect" class="source-select">
                                <option value="all">Tất cả nguồn</option>
                                <option value="nguonc">NguonC Cinema</option>
                                <option value="vsmov">VSMov Cinema</option>
                                <option value="hhpanda">HHPanda 3D</option>
                            </select>
                            <button class="btn btn-primary" onclick="executeSearch()">
                                <i class="fa-solid fa-magnifying-glass"></i> Tìm kiếm
                            </button>
                        </div>
                    </div>

                    <div id="searchResultsContainer">
                        <p style="color: var(--text-dim); text-align: center; padding: 40px;">Hãy nhập từ khóa để tìm kiếm phim trên các nguồn...</p>
                    </div>
                </div>

                <!-- TAB 4: Services & Config -->
                <div class="tab-pane" id="tab-services">
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px;">
                        <div class="stat-card" style="flex-direction: column; align-items: flex-start; gap: 16px;">
                            <h4 style="font-size: 15px; color: #fff; font-family: var(--font-heading); font-weight: 700;">🤖 Trạng Thái Telegram</h4>
                            <div style="font-size: 13px; color: var(--text-muted); line-height: 1.6;">
                                <p>• Channel ID: <span id="cfgTgChannel" style="color: var(--cyan); font-family: var(--font-mono);">Đang tải...</span></p>
                                <p>• User Session: <span id="cfgTgSession">Đang tải...</span></p>
                                <p>• Bot Token: <span id="cfgTgBot">Đang tải...</span></p>
                            </div>
                        </div>

                        <div class="stat-card" style="flex-direction: column; align-items: flex-start; gap: 16px;">
                            <h4 style="font-size: 15px; color: #fff; font-family: var(--font-heading); font-weight: 700;">🚀 Debrid & Dịch Vụ</h4>
                            <div style="font-size: 13px; color: var(--text-muted); line-height: 1.6;">
                                <p>• Real-Debrid: <span id="cfgRdStatus">Đang kiểm tra...</span></p>
                                <p>• TorBox: <span id="cfgTorboxStatus">Đang kiểm tra...</span></p>
                                <p>• qBittorrent: <span id="cfgQbitStatus">Đang kiểm tra...</span></p>
                                <p>• Gemini AI Dịch Sub: <span id="cfgGeminiStatus">Đang kiểm tra...</span></p>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- TAB 5: Logs & Cache -->
                <div class="tab-pane" id="tab-logs">
                    <div style="display: flex; align-items: center; justify-content: space-between;">
                        <div>
                            <h3 style="font-family: var(--font-heading); font-size: 18px; font-weight: 700;">📜 Nhật Ký Hoạt Động Trực Tiếp</h3>
                            <p style="font-size: 13px; color: var(--text-dim);">Theo dõi các lượt kết nối stream và yêu cầu từ Stremio.</p>
                        </div>
                        <div style="display: flex; gap: 10px;">
                            <button class="btn btn-danger btn-sm" onclick="clearSystemCache()">
                                <i class="fa-solid fa-trash"></i> Xóa Toàn Bộ Cache
                            </button>
                            <button class="btn btn-secondary btn-sm" onclick="fetchLogs()">
                                <i class="fa-solid fa-arrows-rotate"></i> Làm mới Log
                            </button>
                        </div>
                    </div>

                    <div class="log-console" id="logConsole">
                        <div class="log-line"><span class="log-time">--:--:--</span><span class="log-msg">Đang kết nối nhật ký máy chủ...</span></div>
                    </div>
                </div>
            </div>
        </main>
    </div>

    <!-- Modal Player -->
    <div class="modal-overlay" id="playerModal">
        <div class="modal-box">
            <div class="modal-header">
                <h3 id="modalMediaTitle" style="font-family: var(--font-heading); font-size: 16px; color: #fff;">Xem Phim</h3>
                <button class="btn btn-secondary btn-sm" onclick="closePlayerModal()">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>
            <div class="modal-body">
                <div class="video-container">
                    <video id="html5VideoPlayer" class="video-player" controls playsinline autoplay></video>
                </div>
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    <h4 style="font-size: 13px; font-weight: 700; color: var(--text-muted);">Danh sách tập:</h4>
                    <div class="episode-chips" id="modalEpisodeChips">
                        <!-- Loaded dynamically -->
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Toast container -->
    <div class="toast-container" id="toastContainer"></div>

    <script>
        let cachedAddonsData = [];
        let hlsInstance = null;

        const tabTitles = {
            'dashboard': '📊 Bảng Điều Khiển Tổng Quan',
            'addons': '🧩 Trung Tâm Cài Đặt Addon',
            'explorer': '🔍 Tra Cứu Phim & Trình Phát Thử',
            'services': '⚙️ Cấu Hình Hệ Thống & Dịch Vụ',
            'logs': '📜 Nhật Ký & Quản Lý Bộ Nhớ Cache'
        };

        function switchTab(tabId) {
            document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));

            const activeBtn = Array.from(document.querySelectorAll('.nav-item')).find(a => a.getAttribute('onclick').includes(tabId));
            if (activeBtn) activeBtn.classList.add('active');

            const targetPane = document.getElementById(`tab-${tabId}`);
            if (targetPane) targetPane.classList.add('active');

            document.getElementById('pageTitle').textContent = tabTitles[tabId] || 'Bảng Điều Khiển';

            if (tabId === 'logs') fetchLogs();
            if (tabId === 'addons') renderAddonCards();
        }

        function showToast(message, icon = 'fa-check') {
            const container = document.getElementById('toastContainer');
            const toast = document.createElement('div');
            toast.className = 'toast';
            toast.innerHTML = `<i class="fa-solid ${icon}" style="color: var(--primary);"></i> <span>${message}</span>`;
            container.appendChild(toast);
            setTimeout(() => {
                toast.style.opacity = '0';
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        }

        function copyToClipboard(text, label = 'Liên kết') {
            navigator.clipboard.writeText(text).then(() => {
                showToast(`Đã sao chép ${label}!`, 'fa-copy');
            }).catch(() => {
                prompt('Sao chép liên kết:', text);
            });
        }

        async function fetchSystemStatus() {
            try {
                const res = await fetch('/api/system/status');
                const data = await res.json();

                document.getElementById('statUptime').textContent = data.uptime || 'N/A';
                document.getElementById('statLanIp').textContent = `${data.lan_ip}:${data.port}`;
                document.getElementById('statCacheEntries').textContent = `${data.stats.moviesdrive_cache_entries || 0} mục`;

                if (data.telegram.connected) {
                    document.getElementById('statTelegram').textContent = `Online (${data.telegram.user || 'OK'})`;
                    document.getElementById('statTelegram').style.color = 'var(--success)';
                } else {
                    document.getElementById('statTelegram').textContent = data.telegram.has_session ? 'Offline' : 'Chưa cấu hình';
                    document.getElementById('statTelegram').style.color = 'var(--warning)';
                }

                // Services tab update
                document.getElementById('cfgTgChannel').textContent = data.telegram.channel_id;
                document.getElementById('cfgTgSession').textContent = data.telegram.has_session ? '✅ Đã cấu hình' : '❌ Chưa có';
                document.getElementById('cfgTgBot').textContent = data.telegram.has_bot_token ? '✅ Đã cấu hình' : '❌ Chưa có';

                document.getElementById('cfgRdStatus').textContent = data.services.real_debrid ? '✅ Kích hoạt' : '❌ Tắt';
                document.getElementById('cfgTorboxStatus').textContent = data.services.torbox ? '✅ Kích hoạt' : '❌ Tắt';
                document.getElementById('cfgQbitStatus').textContent = data.services.qbittorrent ? '✅ Kích hoạt' : '❌ Tắt';
                document.getElementById('cfgGeminiStatus').textContent = data.services.gemini_ai ? '✅ Kích hoạt' : '❌ Tắt';

            } catch (err) {
                console.error('Fetch status failed', err);
            }
        }

        async function fetchAddons() {
            try {
                const res = await fetch('/api/system/addons');
                const data = await res.json();
                cachedAddonsData = data.addons || [];
                renderAddonCards();
            } catch (err) {
                console.error('Fetch addons failed', err);
            }
        }

        function renderAddonCards() {
            const env = document.getElementById('envUrlSelector').value || 'lan';
            const fullGrid = document.getElementById('fullAddonsGrid');
            const overviewGrid = document.getElementById('overviewAddonsGrid');

            let fullHtml = '';
            let overviewHtml = '';

            cachedAddonsData.forEach(addon => {
                const manifestUrl = addon.manifests[env] || addon.manifests['lan'];
                const stremioInstallUrl = manifestUrl.replace('http://', 'stremio://').replace('https://', 'stremio://');
                const stremioWebUrl = `https://web.stremio.com/#/addons?addon=${encodeURIComponent(manifestUrl)}`;

                const cardHtml = `
                    <div class="addon-card">
                        <div class="addon-header">
                            <div class="addon-title-group">
                                <div class="addon-icon">
                                    <i class="fa-solid ${addon.icon}"></i>
                                </div>
                                <div>
                                    <h3>${addon.name}</h3>
                                    <span>${addon.category}</span>
                                </div>
                            </div>
                            <span class="badge-tag">${addon.badge}</span>
                        </div>
                        <p class="addon-desc">${addon.description}</p>
                        <div class="manifest-selector">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <span style="font-size:11px; font-weight:600; color:var(--text-dim);">Manifest URL (${env.toUpperCase()}):</span>
                                <button class="btn btn-secondary btn-sm" style="padding:2px 8px; font-size:10px;" onclick="copyToClipboard('${manifestUrl}', '${addon.name}')">
                                    <i class="fa-solid fa-copy"></i> Copy
                                </button>
                            </div>
                            <div class="manifest-url-row">
                                <input type="text" class="manifest-url-input" value="${manifestUrl}" readonly onclick="this.select()">
                            </div>
                        </div>
                        <div class="addon-actions">
                            <a href="${stremioInstallUrl}" class="btn btn-primary btn-sm" style="justify-content:center;">
                                <i class="fa-solid fa-download"></i> Cài Stremio
                            </a>
                            <a href="${stremioWebUrl}" target="_blank" class="btn btn-secondary btn-sm" style="justify-content:center;">
                                <i class="fa-solid fa-globe"></i> Mở Web
                            </a>
                        </div>
                    </div>
                `;

                fullHtml += cardHtml;
                overviewHtml += cardHtml;
            });

            if (fullGrid) fullGrid.innerHTML = fullHtml;
            if (overviewGrid) overviewGrid.innerHTML = overviewHtml;
        }

        async function executeSearch() {
            const query = document.getElementById('searchInput').value.trim();
            const source = document.getElementById('searchSourceSelect').value;
            if (!query) return;

            const container = document.getElementById('searchResultsContainer');
            container.innerHTML = '<p style="color:var(--text-dim); text-align:center; padding:40px;"><i class="fa-solid fa-spinner fa-spin"></i> Đang tìm kiếm trên các nguồn...</p>';

            try {
                const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&source=${source}`);
                const data = await res.json();
                if (!data.results || data.results.length === 0) {
                    container.innerHTML = `<p style="color:var(--text-dim); text-align:center; padding:40px;">Không tìm thấy kết quả cho từ khóa "<strong>${query}</strong>".</p>`;
                    return;
                }

                let html = `<div class="media-results-grid">`;
                data.results.forEach(item => {
                    html += `
                        <div class="media-card" onclick="openMediaDetail('${item.source_id}', '${item.id.replace(item.source_id + ':', '')}', '${encodeURIComponent(item.title)}')">
                            <div class="media-poster-box">
                                <span class="media-badge-source">${item.source}</span>
                                <span class="media-badge-quality">${item.quality}</span>
                                <img src="${item.poster || 'https://placehold.co/300x450/18181b/ffffff?text=No+Poster'}" class="media-poster-img" loading="lazy" onerror="this.src='https://placehold.co/300x450/18181b/ffffff?text=No+Poster'">
                            </div>
                            <div class="media-info">
                                <h4 class="media-title" title="${item.title}">${item.title}</h4>
                                <span class="media-sub">${item.year || '2025'} • ${item.type === 'movie' ? 'Phim Lẻ' : 'Phim Bộ'}</span>
                            </div>
                        </div>
                    `;
                });
                html += `</div>`;
                container.innerHTML = html;
            } catch (err) {
                container.innerHTML = `<p style="color:var(--danger); text-align:center; padding:40px;">Lỗi khi tìm kiếm: ${err.message}</p>`;
            }
        }

        async function openMediaDetail(source, id, titleEncoded) {
            const title = decodeURIComponent(titleEncoded);
            document.getElementById('modalMediaTitle').textContent = title;
            const chipsContainer = document.getElementById('modalEpisodeChips');
            chipsContainer.innerHTML = '<span style="color:var(--text-dim); font-size:12px;">Đang tải danh sách tập...</span>';

            document.getElementById('playerModal').classList.add('active');

            try {
                const res = await fetch(`/api/media/details?source=${source}&id=${encodeURIComponent(id)}`);
                const data = await res.json();

                if (data.episodes && data.episodes.length > 0) {
                    let chipsHtml = '';
                    data.episodes.forEach((ep, idx) => {
                        const playUrl = ep.m3u8 || ep.embed;
                        chipsHtml += `<button class="ep-chip ${idx === 0 ? 'active' : ''}" onclick="playStreamUrl('${playUrl}', this)">${ep.name || 'Tập ' + (idx + 1)}</button>`;
                    });
                    chipsContainer.innerHTML = chipsHtml;
                    // Play first episode
                    playStreamUrl(data.episodes[0].m3u8 || data.episodes[0].embed);
                } else {
                    chipsContainer.innerHTML = '<span style="color:var(--text-dim); font-size:12px;">Không tìm thấy luồng phát trực tiếp.</span>';
                }
            } catch (err) {
                chipsContainer.innerHTML = `<span style="color:var(--danger); font-size:12px;">Lỗi: ${err.message}</span>`;
            }
        }

        function playStreamUrl(url, chipEl = null) {
            if (chipEl) {
                document.querySelectorAll('.ep-chip').forEach(c => c.classList.remove('active'));
                chipEl.classList.add('active');
            }

            const video = document.getElementById('html5VideoPlayer');
            if (hlsInstance) {
                hlsInstance.destroy();
                hlsInstance = null;
            }

            if (url.includes('.m3u8')) {
                if (Hls.isSupported()) {
                    hlsInstance = new Hls();
                    hlsInstance.loadSource(url);
                    hlsInstance.attachMedia(video);
                    hlsInstance.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}));
                } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                    video.src = url;
                    video.play().catch(() => {});
                }
            } else {
                video.src = url;
                video.play().catch(() => {});
            }
        }

        function closePlayerModal() {
            const video = document.getElementById('html5VideoPlayer');
            video.pause();
            video.src = '';
            if (hlsInstance) {
                hlsInstance.destroy();
                hlsInstance = null;
            }
            document.getElementById('playerModal').classList.remove('active');
        }

        async function fetchLogs() {
            try {
                const res = await fetch('/api/system/logs');
                const data = await res.json();
                const consoleEl = document.getElementById('logConsole');
                if (data.logs && data.logs.length > 0) {
                    consoleEl.innerHTML = data.logs.map(log => `
                        <div class="log-line">
                            <span class="log-time">[${log.time}]</span>
                            <span class="log-lvl-${log.level}">[${log.level}]</span>
                            <span class="log-msg">${log.message}</span>
                        </div>
                    `).join('');
                    consoleEl.scrollTop = consoleEl.scrollHeight;
                }
            } catch (err) {
                console.error('Fetch logs failed', err);
            }
        }

        async function clearSystemCache() {
            try {
                const res = await fetch('/api/cache/clear', { method: 'POST' });
                const data = await res.json();
                showToast(data.message || 'Đã xóa cache!', 'fa-trash');
                fetchSystemStatus();
            } catch (err) {
                showToast('Lỗi khi xóa cache', 'fa-triangle-exclamation');
            }
        }

        // Init
        window.addEventListener('DOMContentLoaded', () => {
            fetchSystemStatus();
            fetchAddons();
            setInterval(fetchSystemStatus, 15000);
        });
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html)
