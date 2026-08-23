import logging
import asyncio
import time
import os
import socket
import urllib.parse
import hashlib
import hmac
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
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
            entry = {
                "time": time.strftime("%H:%M:%S", time.localtime(record.created)),
                "level": record.levelname,
                "name": record.name,
                "message": record.getMessage()
            }
            self.buffer.append(entry)
            if len(self.buffer) > self.capacity:
                self.buffer.pop(0)
        except Exception:
            pass

log_buffer_handler = LogBufferHandler(300)
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


def get_session_secret() -> str:
    seed = f"{getattr(Config, 'API_HASH', 'hash')}_{getattr(Config, 'BOT_TOKEN', 'tok')}_{getattr(Config, 'DASHBOARD_PASSWORD', 'pwd')}_salt_dashboard"
    return hashlib.sha256(seed.encode()).hexdigest()


def generate_session_token(username: str) -> str:
    timestamp = int(time.time())
    secret = get_session_secret()
    sig = hmac.new(secret.encode(), f"{username}:{timestamp}".encode(), hashlib.sha256).hexdigest()
    return f"{username}:{timestamp}:{sig}"


def verify_session_token(token: str) -> bool:
    if not token or ":" not in token:
        return False
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return False
        username, ts_str, sig = parts
        timestamp = int(ts_str)
        # Token valid for 30 days
        if time.time() - timestamp > 30 * 86400:
            return False
        secret = get_session_secret()
        expected_sig = hmac.new(secret.encode(), f"{username}:{timestamp}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected_sig)
    except Exception:
        return False


def is_auth_required() -> bool:
    return bool(Config.DASHBOARD_PASSWORD and str(Config.DASHBOARD_PASSWORD).strip())


def is_authenticated(request: Request) -> bool:
    if not is_auth_required():
        return True
    
    # 1. Cookie check
    cookie_token = request.cookies.get("dashboard_session")
    if cookie_token and verify_session_token(cookie_token):
        return True
        
    # 2. Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if verify_session_token(token) or (Config.DASHBOARD_PASSWORD and token == Config.DASHBOARD_PASSWORD):
            return True
            
    # 3. Query param key / password
    key = request.query_params.get("key") or request.query_params.get("api_key") or request.query_params.get("password")
    if key and (key == Config.DASHBOARD_PASSWORD or verify_session_token(key)):
        return True
        
    return False


def render_login_page() -> str:
    return r"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Đăng Nhập - Stremio Addon Studio</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        :root {
            --bg-body: #09090b;
            --bg-card: rgba(18, 18, 24, 0.8);
            --border-color: rgba(255, 255, 255, 0.08);
            --border-glow: rgba(99, 102, 241, 0.35);
            --primary: #6366f1;
            --primary-hover: #4f46e5;
            --primary-gradient: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
            --text-main: #f4f4f5;
            --text-muted: #a1a1aa;
            --text-dim: #71717a;
            --danger: #ef4444;
            --font-main: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            --font-heading: 'Outfit', sans-serif;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-body);
            color: var(--text-main);
            font-family: var(--font-main);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            overflow: hidden;
            padding: 20px;
        }

        /* Ambient Glow Background */
        .ambient-glow {
            position: absolute;
            width: 500px;
            height: 500px;
            border-radius: 50%;
            filter: blur(120px);
            opacity: 0.18;
            pointer-events: none;
            z-index: 0;
        }
        .glow-1 {
            top: -100px;
            left: -100px;
            background: #6366f1;
        }
        .glow-2 {
            bottom: -100px;
            right: -100px;
            background: #ec4899;
        }
        .glow-3 {
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: #8b5cf6;
            width: 350px;
            height: 350px;
            opacity: 0.1;
        }

        .login-card {
            position: relative;
            z-index: 1;
            width: 100%;
            max-width: 420px;
            background: var(--bg-card);
            backdrop-filter: blur(24px);
            -webkit-backdrop-filter: blur(24px);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 36px 32px;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 255, 255, 0.05);
            animation: fadeIn 0.4s ease;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(16px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .brand-header {
            text-align: center;
            margin-bottom: 28px;
        }

        .brand-icon-box {
            width: 56px;
            height: 56px;
            border-radius: 16px;
            background: var(--primary-gradient);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 26px;
            color: #fff;
            box-shadow: 0 10px 25px rgba(99, 102, 241, 0.4);
            margin-bottom: 16px;
        }

        .brand-title {
            font-family: var(--font-heading);
            font-size: 22px;
            font-weight: 700;
            color: #fff;
            letter-spacing: -0.5px;
        }

        .brand-subtitle {
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 6px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-label {
            display: block;
            font-size: 12.5px;
            font-weight: 600;
            color: var(--text-muted);
            margin-bottom: 8px;
        }

        .input-wrapper {
            position: relative;
            display: flex;
            align-items: center;
        }

        .input-icon {
            position: absolute;
            left: 14px;
            font-size: 14px;
            color: var(--text-dim);
            pointer-events: none;
            transition: color 0.2s ease;
        }

        .form-input {
            width: 100%;
            height: 44px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 0 42px 0 40px;
            color: #fff;
            font-size: 14px;
            font-family: var(--font-main);
            outline: none;
            transition: all 0.2s ease;
        }

        .form-input:focus {
            background: rgba(255, 255, 255, 0.06);
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
        }

        .password-toggle {
            position: absolute;
            right: 14px;
            font-size: 14px;
            color: var(--text-dim);
            cursor: pointer;
            transition: color 0.2s ease;
        }

        .password-toggle:hover {
            color: #fff;
        }

        .form-options {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 24px;
            font-size: 12.5px;
        }

        .remember-label {
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text-muted);
            cursor: pointer;
        }

        .remember-label input {
            cursor: pointer;
            accent-color: var(--primary);
        }

        .btn-submit {
            width: 100%;
            height: 46px;
            background: var(--primary-gradient);
            border: none;
            border-radius: 10px;
            color: #fff;
            font-size: 14.5px;
            font-weight: 700;
            font-family: var(--font-heading);
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(99, 102, 241, 0.35);
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }

        .btn-submit:hover {
            transform: translateY(-1px);
            box-shadow: 0 8px 25px rgba(99, 102, 241, 0.45);
        }

        .btn-submit:active {
            transform: translateY(1px);
        }

        .btn-submit:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }

        .error-alert {
            display: none;
            background: rgba(239, 68, 68, 0.12);
            border: 1px solid rgba(239, 68, 68, 0.3);
            border-radius: 10px;
            padding: 10px 14px;
            color: #fca5a5;
            font-size: 13px;
            margin-bottom: 20px;
            align-items: center;
            gap: 10px;
        }

        .footer-note {
            text-align: center;
            margin-top: 24px;
            font-size: 12px;
            color: var(--text-dim);
        }
    </style>
</head>
<body>
    <div class="ambient-glow glow-1"></div>
    <div class="ambient-glow glow-2"></div>
    <div class="ambient-glow glow-3"></div>

    <div class="login-card">
        <div class="brand-header">
            <div class="brand-icon-box">
                <i class="fa-solid fa-shield-halved"></i>
            </div>
            <h2 class="brand-title">Stremio Addon Studio</h2>
            <p class="brand-subtitle">Đăng nhập để quản trị máy chủ & cấu hình addon</p>
        </div>

        <div id="errorAlert" class="error-alert">
            <i class="fa-solid fa-circle-exclamation"></i>
            <span id="errorText">Tên đăng nhập hoặc mật khẩu không chính xác!</span>
        </div>

        <form id="loginForm" onsubmit="handleLogin(event)">
            <div class="form-group">
                <label class="form-label" for="username">Tên đăng nhập</label>
                <div class="input-wrapper">
                    <i class="fa-solid fa-user input-icon"></i>
                    <input type="text" id="username" class="form-input" placeholder="admin" required autocomplete="username">
                </div>
            </div>

            <div class="form-group">
                <label class="form-label" for="password">Mật khẩu</label>
                <div class="input-wrapper">
                    <i class="fa-solid fa-lock input-icon"></i>
                    <input type="password" id="password" class="form-input" placeholder="Nhập mật khẩu quản trị..." required autocomplete="current-password">
                    <i class="fa-solid fa-eye password-toggle" onclick="togglePasswordVisibility()"></i>
                </div>
            </div>

            <div class="form-options">
                <label class="remember-label">
                    <input type="checkbox" id="rememberMe" checked> Ghi nhớ đăng nhập
                </label>
            </div>

            <button type="submit" id="btnSubmit" class="btn-submit">
                <i class="fa-solid fa-arrow-right-to-bracket"></i> Đăng Nhập
            </button>
        </form>

        <div class="footer-note">
            <span>Bảo mật máy chủ • Multi-Source Media Vault</span>
        </div>
    </div>

    <script>
        function togglePasswordVisibility() {
            const pwdInput = document.getElementById('password');
            const toggleIcon = document.querySelector('.password-toggle');
            if (pwdInput.type === 'password') {
                pwdInput.type = 'text';
                toggleIcon.classList.remove('fa-eye');
                toggleIcon.classList.add('fa-eye-slash');
            } else {
                pwdInput.type = 'password';
                toggleIcon.classList.remove('fa-eye-slash');
                toggleIcon.classList.add('fa-eye');
            }
        }

        async function handleLogin(e) {
            e.preventDefault();
            const btn = document.getElementById('btnSubmit');
            const alertBox = document.getElementById('errorAlert');
            const errorText = document.getElementById('errorText');
            const username = document.getElementById('username').value.trim();
            const password = document.getElementById('password').value;
            const remember = document.getElementById('rememberMe').checked;

            alertBox.style.display = 'none';
            btn.disabled = true;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang xác thực...';

            try {
                const res = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password, remember })
                });
                const data = await res.json();

                if (res.ok && data.success) {
                    btn.innerHTML = '<i class="fa-solid fa-check"></i> Thành công! Đang chuyển hướng...';
                    const params = new URLSearchParams(window.location.search);
                    const redirectUrl = params.get('redirect') || '/dashboard';
                    setTimeout(() => {
                        window.location.href = redirectUrl;
                    }, 400);
                } else {
                    errorText.textContent = data.message || 'Tên đăng nhập hoặc mật khẩu không chính xác!';
                    alertBox.style.display = 'flex';
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fa-solid fa-arrow-right-to-bracket"></i> Đăng Nhập';
                }
            } catch (err) {
                errorText.textContent = 'Lỗi kết nối máy chủ: ' + err.message;
                alertBox.style.display = 'flex';
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-arrow-right-to-bracket"></i> Đăng Nhập';
            }
        }
    </script>
</body>
</html>"""


@dashboard_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if not is_auth_required() or is_authenticated(request):
        return RedirectResponse(url="/dashboard", status_code=302)
    return HTMLResponse(render_login_page())


@dashboard_router.post("/api/auth/login")
async def api_auth_login(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    remember = bool(data.get("remember", True))

    req_user = (Config.DASHBOARD_USERNAME or "admin").strip().lower()
    req_pass = Config.DASHBOARD_PASSWORD or ""

    is_valid = False
    if not req_pass:
        is_valid = True
    else:
        if (username.lower() == req_user or not username) and password == req_pass:
            is_valid = True

    if is_valid:
        token = generate_session_token(username or req_user)
        resp = JSONResponse(content={"success": True, "message": "Đăng nhập thành công!", "token": token, "redirect": "/dashboard"})
        max_age = 30 * 86400 if remember else None
        resp.set_cookie(
            key="dashboard_session",
            value=token,
            max_age=max_age,
            httponly=True,
            samesite="lax",
            path="/"
        )
        logger.info(f"Dashboard user '{username or req_user}' logged in successfully.")
        return resp

    return JSONResponse(status_code=401, content={"success": False, "message": "Tên đăng nhập hoặc mật khẩu không chính xác!"})


@dashboard_router.get("/logout")
@dashboard_router.post("/api/auth/logout")
async def api_auth_logout():
    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie(key="dashboard_session", path="/")
    return resp


def update_env_file(updates: Dict[str, Any]):
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        env_path = ".env"
    
    try:
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        
        updated_keys = set()
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in updates:
                    new_val = str(updates[key])
                    new_lines.append(f"{key}={new_val}\n")
                    updated_keys.add(key)
                    continue
            new_lines.append(line)
            
        for key, val in updates.items():
            if key not in updated_keys:
                new_lines.append(f"\n{key}={val}\n")
                
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception as e:
        logger.warning(f"Failed to update .env file: {e}")


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
            "has_bot_token": bool(Config.BOT_TOKEN),
            "pool": tg_client_manager.get_pool_status() if hasattr(tg_client_manager, "get_pool_status") else {}
        },
        "services": {
            "real_debrid": bool(Config.REAL_DEBRID_API_KEY),
            "torbox": bool(Config.TORBOX_API_KEY),
            "qbittorrent": bool(Config.QBITTORRENT_URL),
            "gemini_ai": bool(Config.GEMINI_API_KEY and Config.ENABLE_GEMINI),
            "enable_subtitles": getattr(Config, "ENABLE_SUBTITLES", True),
            "enable_gemini": Config.ENABLE_GEMINI,
            "enable_custom_ai": Config.ENABLE_CUSTOM_AI,
            "auto_upload": Config.AUTO_UPLOAD_TO_TELEGRAM,
            "auto_vietsub": Config.AUTO_VIET_SUB,
            "auto_thuyet_minh": Config.AUTO_THUYET_MINH,
            "subtitle_offset": Config.SUBTITLE_TIME_OFFSET,
            "gemini_model": Config.GEMINI_MODEL,
            "custom_ai_model": Config.CUSTOM_AI_MODEL,
        },
        "auth": {
            "required": is_auth_required(),
            "username": Config.DASHBOARD_USERNAME or "admin",
            "has_password": bool(Config.DASHBOARD_PASSWORD)
        },
        "stats": {
            "moviesdrive_cache_entries": moviesdrive_cache_count,
            "log_entries": len(log_buffer_handler.buffer)
        }
    }


@dashboard_router.post("/api/config/update")
async def api_update_config(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = dict(request.query_params)
        
    env_updates = {}
    
    if "enable_subtitles" in data:
        val = bool(data["enable_subtitles"]) if not isinstance(data["enable_subtitles"], str) else (data["enable_subtitles"].lower() == "true")
        Config.ENABLE_SUBTITLES = val
        env_updates["ENABLE_SUBTITLES"] = str(val)
        logger.info(f"Dashboard updated config ENABLE_SUBTITLES -> {val}")

    if "auto_vietsub" in data:
        val = bool(data["auto_vietsub"]) if not isinstance(data["auto_vietsub"], str) else (data["auto_vietsub"].lower() == "true")
        Config.AUTO_VIET_SUB = val
        env_updates["AUTO_VIET_SUB"] = str(val)
        logger.info(f"Dashboard updated config AUTO_VIET_SUB -> {val}")

    if "auto_thuyet_minh" in data:
        val = bool(data["auto_thuyet_minh"]) if not isinstance(data["auto_thuyet_minh"], str) else (data["auto_thuyet_minh"].lower() == "true")
        Config.AUTO_THUYET_MINH = val
        env_updates["AUTO_THUYET_MINH"] = str(val)
        logger.info(f"Dashboard updated config AUTO_THUYET_MINH -> {val}")

    if "enable_gemini" in data:
        val = bool(data["enable_gemini"]) if not isinstance(data["enable_gemini"], str) else (data["enable_gemini"].lower() == "true")
        Config.ENABLE_GEMINI = val
        env_updates["ENABLE_GEMINI"] = str(val)
        logger.info(f"Dashboard updated config ENABLE_GEMINI -> {val}")

    if "enable_custom_ai" in data:
        val = bool(data["enable_custom_ai"]) if not isinstance(data["enable_custom_ai"], str) else (data["enable_custom_ai"].lower() == "true")
        Config.ENABLE_CUSTOM_AI = val
        env_updates["ENABLE_CUSTOM_AI"] = str(val)
        logger.info(f"Dashboard updated config ENABLE_CUSTOM_AI -> {val}")

    if "auto_upload" in data:
        val = bool(data["auto_upload"]) if not isinstance(data["auto_upload"], str) else (data["auto_upload"].lower() == "true")
        Config.AUTO_UPLOAD_TO_TELEGRAM = val
        env_updates["AUTO_UPLOAD_TO_TELEGRAM"] = str(val)
        logger.info(f"Dashboard updated config AUTO_UPLOAD_TO_TELEGRAM -> {val}")

    if "subtitle_offset" in data:
        try:
            val = float(data["subtitle_offset"])
            Config.SUBTITLE_TIME_OFFSET = val
            env_updates["SUBTITLE_TIME_OFFSET"] = str(val)
            logger.info(f"Dashboard updated config SUBTITLE_TIME_OFFSET -> {val}")
        except (ValueError, TypeError):
            pass

    if "admin_username" in data:
        val = str(data["admin_username"]).strip()
        if val:
            Config.DASHBOARD_USERNAME = val
            env_updates["DASHBOARD_USERNAME"] = val
            logger.info(f"Dashboard updated config DASHBOARD_USERNAME -> {val}")

    if "admin_password" in data:
        val = str(data["admin_password"]).strip()
        Config.DASHBOARD_PASSWORD = val
        env_updates["DASHBOARD_PASSWORD"] = val
        logger.info("Dashboard updated config DASHBOARD_PASSWORD")

    if "film4k_cookie" in data:
        val = str(data["film4k_cookie"]).strip()
        if val:
            Config.FILM4K_COOKIE = val
            env_updates["FILM4K_COOKIE"] = val
            logger.info("Dashboard updated config FILM4K_COOKIE")

    # Source Enablement Toggles & Board Display Toggles
    source_keys = {
        "enable_source_telegram": "ENABLE_SOURCE_TELEGRAM",
        "enable_source_telegram_debrid": "ENABLE_SOURCE_TELEGRAM",
        "enable_source_nguonc": "ENABLE_SOURCE_NGUONC",
        "enable_source_vsmov": "ENABLE_SOURCE_VSMOV",
        "enable_source_hhpanda": "ENABLE_SOURCE_HHPANDA",
        "enable_source_moviesdrive": "ENABLE_SOURCE_MOVIESDRIVE",
        "enable_source_hdhub4u": "ENABLE_SOURCE_HDHUB4U",
        "enable_source_uhdmovies": "ENABLE_SOURCE_UHDMOVIES",
        "enable_source_4khdhub": "ENABLE_SOURCE_4KHDHUB",
        "enable_source_topxx": "ENABLE_SOURCE_TOPXX",
        "enable_source_hdtoday": "ENABLE_SOURCE_HDTODAY",
        "enable_source_vidking": "ENABLE_SOURCE_VIDKING",
        "enable_source_ernax": "ENABLE_SOURCE_ERNAX",
        "enable_source_film4k_tv": "ENABLE_SOURCE_FILM4K_TV",
        "enable_source_film4k": "ENABLE_SOURCE_FILM4K_TV",
        "enable_source_iptv": "ENABLE_SOURCE_IPTV",
        "enable_source_iptv_org": "ENABLE_SOURCE_IPTV",
        "enable_source_subtitles": "ENABLE_SUBTITLES",
        "enable_source_subtitle": "ENABLE_SUBTITLES",
        "enable_subtitles": "ENABLE_SUBTITLES",
        # Board (Home Screen) Toggles
        "enable_board_telegram": "ENABLE_BOARD_TELEGRAM",
        "enable_board_telegram_debrid": "ENABLE_BOARD_TELEGRAM",
        "enable_board_nguonc": "ENABLE_BOARD_NGUONC",
        "enable_board_vsmov": "ENABLE_BOARD_VSMOV",
        "enable_board_hhpanda": "ENABLE_BOARD_HHPANDA",
        "enable_board_moviesdrive": "ENABLE_BOARD_MOVIESDRIVE",
        "enable_board_hdhub4u": "ENABLE_BOARD_HDHUB4U",
        "enable_board_uhdmovies": "ENABLE_BOARD_UHDMOVIES",
        "enable_board_4khdhub": "ENABLE_BOARD_4KHDHUB",
        "enable_board_topxx": "ENABLE_BOARD_TOPXX",
        "enable_board_hdtoday": "ENABLE_BOARD_HDTODAY",
        "enable_board_vidking": "ENABLE_BOARD_VIDKING",
        "enable_board_ernax": "ENABLE_BOARD_ERNAX",
        "enable_board_film4k_tv": "ENABLE_BOARD_FILM4K_TV",
        "enable_board_film4k": "ENABLE_BOARD_FILM4K_TV",
        "enable_board_iptv": "ENABLE_BOARD_IPTV",
        "enable_board_iptv_org": "ENABLE_BOARD_IPTV",
    }
    for req_k, cfg_k in source_keys.items():
        if req_k in data:
            val = bool(data[req_k]) if not isinstance(data[req_k], str) else (data[req_k].lower() == "true")
            setattr(Config, cfg_k, val)
            env_updates[cfg_k] = str(val)
            logger.info(f"Dashboard updated config {cfg_k} -> {val}")

    if env_updates:
        update_env_file(env_updates)

    return {
        "success": True,
        "message": "Đã cập nhật và lưu cấu hình thành công!",
        "services": {
            "enable_subtitles": getattr(Config, "ENABLE_SUBTITLES", True),
            "auto_vietsub": Config.AUTO_VIET_SUB,
            "auto_thuyet_minh": Config.AUTO_THUYET_MINH,
            "enable_gemini": Config.ENABLE_GEMINI,
            "enable_custom_ai": Config.ENABLE_CUSTOM_AI,
            "auto_upload": Config.AUTO_UPLOAD_TO_TELEGRAM,
            "subtitle_offset": Config.SUBTITLE_TIME_OFFSET,
            "admin_username": Config.DASHBOARD_USERNAME
        },
        "sources": {
            "telegram": getattr(Config, "ENABLE_SOURCE_TELEGRAM", True),
            "nguonc": getattr(Config, "ENABLE_SOURCE_NGUONC", True),
            "vsmov": getattr(Config, "ENABLE_SOURCE_VSMOV", True),
            "hhpanda": getattr(Config, "ENABLE_SOURCE_HHPANDA", True),
            "moviesdrive": getattr(Config, "ENABLE_SOURCE_MOVIESDRIVE", True),
            "hdhub4u": getattr(Config, "ENABLE_SOURCE_HDHUB4U", True),
            "uhdmovies": getattr(Config, "ENABLE_SOURCE_UHDMOVIES", True),
            "4khdhub": getattr(Config, "ENABLE_SOURCE_4KHDHUB", True),
            "topxx": getattr(Config, "ENABLE_SOURCE_TOPXX", True),
            "hdtoday": getattr(Config, "ENABLE_SOURCE_HDTODAY", True),
            "vidking": getattr(Config, "ENABLE_SOURCE_VIDKING", True),
            "ernax": getattr(Config, "ENABLE_SOURCE_ERNAX", True),
            "film4k_tv": getattr(Config, "ENABLE_SOURCE_FILM4K_TV", True),
            "iptv": getattr(Config, "ENABLE_SOURCE_IPTV", True),
        },
        "board": {
            "telegram": getattr(Config, "ENABLE_BOARD_TELEGRAM", True),
            "nguonc": getattr(Config, "ENABLE_BOARD_NGUONC", True),
            "vsmov": getattr(Config, "ENABLE_BOARD_VSMOV", True),
            "hhpanda": getattr(Config, "ENABLE_BOARD_HHPANDA", True),
            "moviesdrive": getattr(Config, "ENABLE_BOARD_MOVIESDRIVE", True),
            "hdhub4u": getattr(Config, "ENABLE_BOARD_HDHUB4U", True),
            "uhdmovies": getattr(Config, "ENABLE_BOARD_UHDMOVIES", True),
            "4khdhub": getattr(Config, "ENABLE_BOARD_4KHDHUB", True),
            "topxx": getattr(Config, "ENABLE_BOARD_TOPXX", False),
            "hdtoday": getattr(Config, "ENABLE_BOARD_HDTODAY", True),
            "vidking": getattr(Config, "ENABLE_BOARD_VIDKING", True),
            "ernax": getattr(Config, "ENABLE_BOARD_ERNAX", True),
            "film4k_tv": getattr(Config, "ENABLE_BOARD_FILM4K_TV", True),
            "iptv": getattr(Config, "ENABLE_BOARD_IPTV", True),
        }
    }


@dashboard_router.get("/api/system/addons")
async def api_system_addons(request: Request):
    lan_ip = get_lan_ip()
    port = Config.PORT
    domain_url = Config.ADDON_URL.rstrip("/") if getattr(Config, "ADDON_URL", None) else str(request.base_url).rstrip("/")
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
            "enabled": bool(getattr(Config, "ENABLE_SOURCE_TELEGRAM", True)),
            "board_enabled": bool(getattr(Config, "ENABLE_BOARD_TELEGRAM", True)),
            "description": "Phát phim trực tiếp từ kênh Telegram riêng tư, Range Requests tua nhanh tức thì, Debrid CDN stream & tải torrent qBittorrent.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/manifest.json{api_key_suffix}",
                "lan": f"http://{lan_ip}:{port}/manifest.json{api_key_suffix}",
                "public": f"{domain_url}/manifest.json{api_key_suffix}"
            },
            "routes": ["/manifest.json", "/stream", "/meta", "/catalog"]
        },
        {
            "id": "iptv",
            "name": "IPTV Org Global Live TV",
            "tag": "200+ Quốc Gia Toàn Cầu",
            "category": "Live TV & M3U8",
            "icon": "fa-satellite-dish",
            "badge": "200+ Nước",
            "badge_color": "cyan",
            "enabled": bool(getattr(Config, "ENABLE_SOURCE_IPTV", True)),
            "board_enabled": bool(getattr(Config, "ENABLE_BOARD_IPTV", True)),
            "description": "Kho kênh truyền hình trực tiếp công khai miễn phí từ hơn 200 quốc gia (Việt Nam, Mỹ, Anh, Nhật Bản, Hàn Quốc, Pháp, Đức, v.v.) từ iptv-org/iptv. Hỗ trợ Stremio Addon & Web TV Player.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/iptv/manifest.json",
                "lan": f"http://{lan_ip}:{port}/iptv/manifest.json",
                "public": f"{domain_url}/iptv/manifest.json"
            },
            "player_url": f"{domain_url}/iptv/tv",
            "routes": ["/iptv/manifest.json", "/iptv/catalog", "/iptv/meta", "/iptv/stream", "/iptv/tv", "/iptv/player"]
        },
        {
            "id": "film4k_tv",
            "name": "Film4k Live TV & Thể Thao",
            "tag": "200+ Kênh TV & Trực Tiếp",
            "category": "Live TV & IPTV M3U",
            "icon": "fa-tv",
            "badge": "200+ Kênh",
            "badge_color": "emerald",
            "enabled": bool(getattr(Config, "ENABLE_SOURCE_FILM4K_TV", True)),
            "board_enabled": bool(getattr(Config, "ENABLE_BOARD_FILM4K_TV", True)),
            "description": "Xem 200+ kênh truyền hình Việt Nam (VTV, HTV, K+, VTC, 63 đài địa phương), Kênh Quốc Tế & Sự kiện thể thao trực tiếp từ Film4k. Hỗ trợ Stremio Addon & M3U Playlist cho TiviMate / VLC.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/film4k/manifest.json",
                "lan": f"http://{lan_ip}:{port}/film4k/manifest.json",
                "public": f"{domain_url}/film4k/manifest.json"
            },
            "playlist_url": f"{domain_url}/film4k/playlist.m3u",
            "player_url": f"{domain_url}/film4k/tv",
            "routes": ["/film4k/manifest.json", "/film4k/catalog", "/film4k/stream", "/film4k/playlist.m3u", "/film4k/tv"]
        },
        {
            "id": "ernax",
            "name": "Ernax Player",
            "tag": "Phim & Series 4K / HD",
            "category": "4K / 1080p HLS & Sub",
            "icon": "fa-play-circle",
            "badge": "Ultra Speed",
            "badge_color": "red",
            "enabled": bool(getattr(Config, "ENABLE_SOURCE_ERNAX", True)),
            "board_enabled": bool(getattr(Config, "ENABLE_BOARD_ERNAX", True)),
            "description": "Kho phim lẻ & series truyền hình chất lượng 4K UHD, 1080p FHD, 720p HLS trực tiếp từ Ernax Player (ernax.pro) kèm phụ đề đa ngôn ngữ.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/ernax/manifest.json",
                "lan": f"http://{lan_ip}:{port}/ernax/manifest.json",
                "public": f"{domain_url}/ernax/manifest.json"
            },
            "routes": ["/ernax/manifest.json", "/ernax/catalog", "/ernax/stream"]
        },
        {
            "id": "vidking",
            "name": "Vidking Player",
            "tag": "Phim & Series Quốc Tế",
            "category": "4K / 1080p HLS & MP4",
            "icon": "fa-crown",
            "badge": "Multi-Server",
            "badge_color": "purple",
            "enabled": bool(getattr(Config, "ENABLE_SOURCE_VIDKING", True)),
            "board_enabled": bool(getattr(Config, "ENABLE_BOARD_VIDKING", True)),
            "description": "Xem phim lẻ & series truyền hình từ Vidking Player (vidking.net) với server Yoru (HLS 4K/1080p), Cypher (Direct MP4) và nhiều server dự phòng.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/vidking/manifest.json",
                "lan": f"http://{lan_ip}:{port}/vidking/manifest.json",
                "public": f"{domain_url}/vidking/manifest.json"
            },
            "routes": ["/vidking/manifest.json", "/vidking/catalog", "/vidking/stream"]
        },
        {
            "id": "hdtoday",
            "name": "HDToday Cinema",
            "tag": "Kho Phim & Series Quốc Tế",
            "category": "Full HD / Multi-Audio & Sub",
            "icon": "fa-globe",
            "badge": "Global HD",
            "badge_color": "blue",
            "enabled": bool(getattr(Config, "ENABLE_SOURCE_HDTODAY", True)),
            "board_enabled": bool(getattr(Config, "ENABLE_BOARD_HDTODAY", True)),
            "description": "Xem phim lẻ & series truyền hình quốc tế từ HDToday (hdtoday.sc), phát trực tiếp HLS Full HD đa âm thanh & phụ đề.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/hdtoday/manifest.json",
                "lan": f"http://{lan_ip}:{port}/hdtoday/manifest.json",
                "public": f"{domain_url}/hdtoday/manifest.json"
            },
            "routes": ["/hdtoday/manifest.json", "/hdtoday/catalog", "/hdtoday/stream"]
        },
        {
            "id": "nguonc",
            "name": "NguonC Cinema",
            "tag": "Kho Phim Tổng Hợp",
            "category": "VietSub & Thuyết Minh",
            "icon": "fa-film",
            "badge": "22 Thể Loại",
            "badge_color": "emerald",
            "enabled": bool(getattr(Config, "ENABLE_SOURCE_NGUONC", True)),
            "board_enabled": bool(getattr(Config, "ENABLE_BOARD_NGUONC", True)),
            "description": "Tích hợp toàn bộ API NguonC với Phim Lẻ, Phim Bộ, TV Shows, Hoạt Hình. Tự động giải mã HLS .m3u8 proxy.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/nguonc/manifest.json",
                "lan": f"http://{lan_ip}:{port}/nguonc/manifest.json",
                "public": f"{domain_url}/nguonc/manifest.json"
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
            "enabled": bool(getattr(Config, "ENABLE_SOURCE_VSMOV", True)),
            "board_enabled": bool(getattr(Config, "ENABLE_BOARD_VSMOV", True)),
            "description": "Kho phim Châu Á và Âu Mỹ vietsub/thuyết minh tốc độ cao, chất lượng sắc nét Full HD / 4K không quảng cáo.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/vsmov/manifest.json",
                "lan": f"http://{lan_ip}:{port}/vsmov/manifest.json",
                "public": f"{domain_url}/vsmov/manifest.json"
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
            "enabled": bool(getattr(Config, "ENABLE_SOURCE_HHPANDA", True)),
            "board_enabled": bool(getattr(Config, "ENABLE_BOARD_HHPANDA", True)),
            "description": "Kho phim Hoạt Hình 3D Trung Quốc siêu nét 4K/1080P: Tiên Nghịch, Đấu Phá Thương Khung, Thế Giới Hoàn Mỹ, Phàm Nhân Tu Tiên...",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/hhpanda/manifest.json",
                "lan": f"http://{lan_ip}:{port}/hhpanda/manifest.json",
                "public": f"{domain_url}/hhpanda/manifest.json"
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
            "enabled": bool(getattr(Config, "ENABLE_SOURCE_MOVIESDRIVE", True)),
            "board_enabled": bool(getattr(Config, "ENABLE_BOARD_MOVIESDRIVE", True)),
            "description": "Phim bom tấn 4K UHD, 1080p từ MoviesDrive. Tự động giải mã link HubCloud, GDFlix, DoodStream và khớp mã IMDb khi duyệt phim.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/moviesdrive/manifest.json",
                "lan": f"http://{lan_ip}:{port}/moviesdrive/manifest.json",
                "public": f"{domain_url}/moviesdrive/manifest.json"
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
            "enabled": bool(getattr(Config, "ENABLE_SOURCE_HDHUB4U", True)),
            "board_enabled": bool(getattr(Config, "ENABLE_BOARD_HDHUB4U", True)),
            "description": "Kho phim Hollywood / Bollywood Dual Audio chất lượng cao, hạ tầng CDN Cloudflare R2 / FastDL 10Gbps phát mượt mà.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/hdhub4u/manifest.json",
                "lan": f"http://{lan_ip}:{port}/hdhub4u/manifest.json",
                "public": f"{domain_url}/hdhub4u/manifest.json"
            },
            "routes": ["/hdhub4u/manifest.json", "/hdhub4u/catalog", "/hdhub4u/stream"]
        },
        {
            "id": "uhdmovies",
            "name": "UHDMovies 4K Cinema",
            "tag": "4K UHD & 1080p HEVC",
            "category": "Ultra HD / HDR DoVi",
            "icon": "fa-gem",
            "badge": "4K 60FPS",
            "badge_color": "amber",
            "enabled": bool(getattr(Config, "ENABLE_SOURCE_UHDMOVIES", True)),
            "board_enabled": bool(getattr(Config, "ENABLE_BOARD_UHDMOVIES", True)),
            "description": "Kho phim Ultra HD 4K 2160p, 4K HDR/Dolby Vision, 1080p 10Bit HEVC, 60FPS từ UHDMovies (uhdmovies.autos) với Google Drive CDN stream trực tiếp siêu tốc.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/uhdmovies/manifest.json",
                "lan": f"http://{lan_ip}:{port}/uhdmovies/manifest.json",
                "public": f"{domain_url}/uhdmovies/manifest.json"
            },
            "routes": ["/uhdmovies/manifest.json", "/uhdmovies/catalog", "/uhdmovies/meta", "/uhdmovies/stream", "/uhdmovies/playback"]
        },
        {
            "id": "4khdhub",
            "name": "4KHDHub Cinema",
            "tag": "4K UHD & Dolby Vision",
            "category": "Ultra HD / Dolby Vision",
            "icon": "fa-film",
            "badge": "4K DV HDR",
            "badge_color": "purple",
            "enabled": bool(getattr(Config, "ENABLE_SOURCE_4KHDHUB", True)),
            "board_enabled": bool(getattr(Config, "ENABLE_BOARD_4KHDHUB", True)),
            "description": "Kho phim & series 4K UHD 2160p, Dolby Vision, HDR10+, 1080p HEVC REMUX từ 4KHDHub (4khdhub.one) với hạ tầng Cloudflare R2 & 10Gbps CDN trực tiếp.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/4khdhub/manifest.json",
                "lan": f"http://{lan_ip}:{port}/4khdhub/manifest.json",
                "public": f"{domain_url}/4khdhub/manifest.json"
            },
            "routes": ["/4khdhub/manifest.json", "/4khdhub/catalog", "/4khdhub/meta", "/4khdhub/stream", "/4khdhub/playback"]
        },
        {
            "id": "topxx",
            "name": "TopXX Cinema",
            "tag": "Kho Phim 18+",
            "category": "Adult Streaming",
            "icon": "fa-heart",
            "badge": "18+ Only",
            "badge_color": "red",
            "enabled": bool(getattr(Config, "ENABLE_SOURCE_TOPXX", True)),
            "board_enabled": bool(getattr(Config, "ENABLE_BOARD_TOPXX", False)),
            "description": "Kho phim giải trí 18+ chất lượng cao phân loại theo thể loại, diễn viên và hỗ trợ phát trực tiếp trên Stremio.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/topxx/manifest.json",
                "lan": f"http://{lan_ip}:{port}/topxx/manifest.json",
                "public": f"{domain_url}/topxx/manifest.json"
            },
            "routes": ["/topxx/manifest.json", "/topxx/catalog", "/topxx/stream"]
        },
        {
            "id": "subtitles",
            "name": "AI VietSub & Subtitles Engine",
            "tag": "Phụ Đề & VietSub AI",
            "category": "OpenSubtitles & AI Translation",
            "icon": "fa-closed-captioning",
            "badge": "Subtitles",
            "badge_color": "emerald",
            "enabled": bool(getattr(Config, "ENABLE_SUBTITLES", True)),
            "board_enabled": False,
            "is_subtitle_engine": True,
            "description": "Kho phụ đề đa ngôn ngữ OpenSubtitles và tự động dịch phụ đề chuẩn tiếng Việt (VietSub) siêu tốc qua Gemini / Claude AI cho mọi nguồn phim Stremio.",
            "manifests": {
                "local": f"http://127.0.0.1:{port}/subtitles/manifest.json{api_key_suffix}",
                "lan": f"http://{lan_ip}:{port}/subtitles/manifest.json{api_key_suffix}",
                "public": f"{domain_url}/subtitles/manifest.json{api_key_suffix}"
            },
            "routes": ["/subtitles/manifest.json", "/subtitles", "/subtitles/vtt", "/subtitles/srt"]
        }
    ]
    return {"addons": addons}


@dashboard_router.get("/api/system/logs")
async def api_system_logs():
    return {"logs": log_buffer_handler.buffer[-250:]}


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

    try:
        from film4k_router import _film4k_cache
        f_count = len(_film4k_cache)
        _film4k_cache.clear()
        cleared.append(f"Film4k Live TV Cache ({f_count} entries)")
    except Exception:
        pass

    try:
        from iptv_router import _iptv_cache
        i_count = len(_iptv_cache)
        _iptv_cache.clear()
        cleared.append(f"IPTV Org Channels Cache ({i_count} entries)")
    except Exception:
        pass

    logger.info(f"Admin Dashboard cleared caches: {', '.join(cleared)}")
    return {"success": True, "message": "Đã xóa toàn bộ bộ nhớ đệm thành công!", "cleared": cleared}


@dashboard_router.get("/api/search")
async def api_universal_search(request: Request, q: str = Query(..., min_length=1), source: Optional[str] = None):
    query = q.strip()
    results = []
    base_url = str(request.base_url).rstrip("/")

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
                        poster = item.get("thumb_url", "") or item.get("poster_url", "")
                        if poster and not poster.startswith("http"):
                            poster = f"https://phim.nguonc.com{poster}" if poster.startswith("/") else f"https://phim.nguonc.com/{poster}"
                        items.append({
                            "id": f"nguonc:{slug}",
                            "title": item.get("name", "Unknown"),
                            "original_title": item.get("original_name", ""),
                            "source": "NguonC Cinema",
                            "source_id": "nguonc",
                            "poster": poster,
                            "year": item.get("year", "2025"),
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
            url = f"https://vsmov.com/api/tim-kiem?keyword={urllib.parse.quote(query)}"
            headers = {"User-Agent": "Mozilla/5.0"}
            async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    for item in data.get("items", [])[:10]:
                        slug = item.get("slug") or item.get("id", "")
                        poster = item.get("thumb_url") or item.get("poster_url") or ""
                        if poster and not poster.startswith("http"):
                            poster = f"https://vsmov.com{poster}" if poster.startswith("/") else f"https://vsmov.com/{poster}"
                        items.append({
                            "id": f"vsmov:{slug}",
                            "title": item.get("name", ""),
                            "original_title": item.get("origin_name", ""),
                            "source": "VSMov Cinema",
                            "source_id": "vsmov",
                            "poster": poster,
                            "year": str(item.get("year", "2025")),
                            "quality": item.get("quality", "Full HD"),
                            "type": "series" if item.get("type") in ["hoathinh", "series", "tvshows"] else "movie",
                            "detail_url": f"/api/media/details?source=vsmov&id={slug}"
                        })
        except Exception as e:
            logger.warning(f"Dashboard search VSMov error: {e}")
        return items

    async def search_hhpanda():
        items = []
        try:
            url = f"https://hhpanda.st/?s={urllib.parse.quote(query)}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://hhpanda.st/"}
            async with httpx.AsyncClient(timeout=8.0, headers=headers, follow_redirects=True) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    import re
                    pattern = r'<a\s+href="https://hhpanda\.st/([^"]+)"[^>]*title="([^"]+)"[^>]*>.*?<img[^>]+(?:data-src|src)="([^"]+)"'
                    matches = re.findall(pattern, res.text, re.DOTALL)
                    if not matches:
                        matches = re.findall(r'<a\s+href="https://hhpanda\.st/([^"]+)"[^>]*>.*?<img[^>]+(?:data-src|src)="([^"]+)"[^>]*alt="([^"]+)"', res.text, re.DOTALL)
                        matches = [(m[0], m[2], m[1]) for m in matches]
                    for match in matches[:10]:
                        slug, title, poster = match
                        slug_clean = slug.strip("/")
                        if not slug_clean.startswith("the-loai") and not slug_clean.startswith("country") and not slug_clean.startswith("page"):
                            items.append({
                                "id": f"hhpanda:{slug_clean}",
                                "title": title,
                                "original_title": "HH3D 4K",
                                "source": "HHPanda 3D",
                                "source_id": "hhpanda",
                                "poster": poster,
                                "year": "4K Ultra HD",
                                "quality": "4K/1080P",
                                "type": "series",
                                "detail_url": f"/api/media/details?source=hhpanda&id={slug_clean}"
                            })
        except Exception as e:
            logger.warning(f"Dashboard search HHPanda error: {e}")
        return items

    async def search_moviesdrive():
        items = []
        try:
            from moviesdrive_catalog import search_moviesdrive_api, clean_title, looks_like_series
            import re
            data = await search_moviesdrive_api(query, page=1)
            for hit in data.get("hits", [])[:10]:
                doc = hit.get("document", {})
                slug = (doc.get("permalink") or "").strip("/")
                if not slug:
                    continue
                raw_title = doc.get("post_title", "Untitled")
                cleaned = clean_title(raw_title) or raw_title
                poster = doc.get("post_thumbnail", "")
                year_match = re.search(r"\b(19\d\d|20\d\d)\b", raw_title)
                year = year_match.group(1) if year_match else "2025"
                items.append({
                    "id": f"moviesdrive:{slug}",
                    "title": cleaned,
                    "original_title": raw_title,
                    "source": "MoviesDrive",
                    "source_id": "moviesdrive",
                    "poster": poster,
                    "year": year,
                    "quality": "10Gbps CDN",
                    "type": "series" if looks_like_series(raw_title) else "movie",
                    "detail_url": f"/api/media/details?source=moviesdrive&id={slug}"
                })
        except Exception as e:
            logger.warning(f"Dashboard search MoviesDrive error: {e}")
        return items

    async def search_hdhub4u():
        items = []
        try:
            from hdhub4u_catalog import search_hdhub4u as hdh_search
            raw_items = await hdh_search(query, page=1)
            for it in raw_items[:10]:
                slug = it.get("slug") or it.get("id", "").replace("hdhub4u:", "")
                if not slug:
                    continue
                items.append({
                    "id": f"hdhub4u:{slug}",
                    "title": it.get("name", "Untitled"),
                    "original_title": it.get("name", ""),
                    "source": "HDHub4u",
                    "source_id": "hdhub4u",
                    "poster": it.get("poster", ""),
                    "year": "2025",
                    "quality": "FastDL CDN",
                    "type": it.get("type", "movie"),
                    "detail_url": f"/api/media/details?source=hdhub4u&id={slug}"
                })
        except Exception as e:
            logger.warning(f"Dashboard search HDHub4u error: {e}")
        return items

    async def search_topxx():
        items = []
        try:
            url = f"https://topxx.vip/api/v1/movies/search?q={urllib.parse.quote(query)}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    for it in data.get("data", [])[:10]:
                        code = it.get("code", "")
                        trans = it.get("trans", [])
                        title = next((t.get("name") for t in trans if t.get("locale") in ["vi", "en"]), None) or (trans[0].get("name") if trans else code)
                        poster = it.get("thumbnail", "")
                        quality = it.get("quality", "1080p")
                        items.append({
                            "id": f"topxx:{code}",
                            "title": title or "TopXX Movie",
                            "original_title": code,
                            "source": "TopXX Cinema",
                            "source_id": "topxx",
                            "poster": poster,
                            "year": "18+ Adult",
                            "quality": quality or "Full HD",
                            "type": "movie",
                            "detail_url": f"/api/media/details?source=topxx&id={code}"
                        })
        except Exception as e:
            logger.warning(f"Dashboard search TopXX error: {e}")
        return items

    async def search_telegram():
        items = []
        try:
            if tg_client_manager.client and tg_client_manager.client.is_connected:
                messages = await tg_client_manager.search_messages(query, limit=10)
                for msg in messages:
                    doc = getattr(msg, "document", None) or getattr(msg, "video", None)
                    fname = getattr(doc, "file_name", None) or (getattr(msg, "caption", "") or getattr(msg, "text", "") or f"Telegram_Media_{msg.id}")[:60]
                    fsize = getattr(doc, "file_size", 0)
                    size_str = f"{fsize / (1024*1024):.1f} MB" if fsize else "Telegram Stream"
                    chat_id = msg.chat.id
                    items.append({
                        "id": f"telegram:{chat_id}:{msg.id}",
                        "title": fname,
                        "original_title": fname,
                        "source": "Telegram Vault",
                        "source_id": "telegram",
                        "poster": "/stremio_telegram_banner.png",
                        "year": time.strftime("%Y-%m-%d", time.localtime(msg.date)) if getattr(msg, "date", None) else "TG Vault",
                        "quality": size_str,
                        "type": "movie",
                        "detail_url": f"/api/media/details?source=telegram&id={chat_id}:{msg.id}"
                    })
        except Exception as e:
            logger.warning(f"Dashboard search Telegram error: {e}")
        return items

    async def search_hdtoday():
        items = []
        try:
            from hdtoday_router import hdtoday_fetch_html, parse_flw_items
            base_url = getattr(Config, "HDTODAY_BASE_URL", "https://hdtoday.sc").rstrip("/")
            kw = urllib.parse.quote(query.strip())
            html = await hdtoday_fetch_html(f"{base_url}/search/{kw}?page=1", ttl=300)
            if html:
                metas = parse_flw_items(html)
                for m in metas[:15]:
                    slug_id = m.get("id", "").replace("hdtoday:movie:", "").replace("hdtoday:series:", "")
                    items.append({
                        "id": m.get("id"),
                        "title": m.get("name"),
                        "original_title": m.get("name"),
                        "source": "HDToday Cinema",
                        "source_id": "hdtoday",
                        "poster": m.get("poster"),
                        "year": m.get("description", "HDToday HD"),
                        "quality": "Full HD / 4K",
                        "type": m.get("type", "movie"),
                        "detail_url": f"/api/media/details?source=hdtoday&id={slug_id}"
                    })
        except Exception as e:
            logger.warning(f"Dashboard search HDToday error: {e}")
        return items

    async def search_ernax():
        items = []
        try:
            from ernax_router import ernax_search
            results = await ernax_search(query.strip(), max_results=15)
            for m in results:
                raw_id = m.get("id", "").replace("ernax:movie:", "").replace("ernax:series:", "")
                items.append({
                    "id": m.get("id"),
                    "title": m.get("name") or m.get("title"),
                    "original_title": m.get("title"),
                    "source": "Ernax Player",
                    "source_id": "ernax",
                    "poster": m.get("poster"),
                    "year": m.get("year", "4K/HD"),
                    "quality": "4K UHD / 1080p",
                    "type": m.get("type", "movie"),
                    "detail_url": f"/api/media/details?source=ernax&id={raw_id}&type={m.get('type', 'movie')}"
                })
        except Exception as e:
            logger.warning(f"Dashboard search Ernax error: {e}")
        return items

    async def search_vidking():
        items = []
        try:
            from vidking_router import vidking_search
            results = await vidking_search(query.strip(), max_results=15)
            for m in results:
                raw_id = m.get("id", "").replace("vidking:movie:", "").replace("vidking:series:", "")
                items.append({
                    "id": m.get("id"),
                    "title": m.get("name") or m.get("title"),
                    "original_title": m.get("title"),
                    "source": "Vidking Player",
                    "source_id": "vidking",
                    "poster": m.get("poster"),
                    "year": m.get("year", "4K/HD"),
                    "quality": "4K UHD / 1080p",
                    "type": m.get("type", "movie"),
                    "detail_url": f"/api/media/details?source=vidking&id={raw_id}&type={m.get('type', 'movie')}"
                })
        except Exception as e:
            logger.warning(f"Dashboard search Vidking error: {e}")
        return items

    tasks = []
    if getattr(Config, "ENABLE_SOURCE_ERNAX", True) and (not source or source == "all" or source == "ernax"):
        tasks.append(search_ernax())
    if getattr(Config, "ENABLE_SOURCE_VIDKING", True) and (not source or source == "all" or source == "vidking"):
        tasks.append(search_vidking())
    if getattr(Config, "ENABLE_SOURCE_HDTODAY", True) and (not source or source == "all" or source == "hdtoday"):
        tasks.append(search_hdtoday())
    if getattr(Config, "ENABLE_SOURCE_NGUONC", True) and (not source or source == "all" or source == "nguonc"):
        tasks.append(search_nguonc())
    if getattr(Config, "ENABLE_SOURCE_VSMOV", True) and (not source or source == "all" or source == "vsmov"):
        tasks.append(search_vsmov())
    if getattr(Config, "ENABLE_SOURCE_HHPANDA", True) and (not source or source == "all" or source == "hhpanda"):
        tasks.append(search_hhpanda())
    if getattr(Config, "ENABLE_SOURCE_MOVIESDRIVE", True) and (not source or source == "all" or source == "moviesdrive"):
        tasks.append(search_moviesdrive())
    if getattr(Config, "ENABLE_SOURCE_HDHUB4U", True) and (not source or source == "all" or source == "hdhub4u"):
        tasks.append(search_hdhub4u())
    if getattr(Config, "ENABLE_SOURCE_TOPXX", True) and (not source or source == "all" or source == "topxx"):
        tasks.append(search_topxx())
    if getattr(Config, "ENABLE_SOURCE_TELEGRAM", True) and (not source or source == "all" or source == "telegram"):
        tasks.append(search_telegram())

    results_lists = await asyncio.gather(*tasks, return_exceptions=True)
    for res_list in results_lists:
        if isinstance(res_list, list):
            results.extend(res_list)

    return {"query": query, "total": len(results), "results": results}


@dashboard_router.get("/api/media/details")
async def api_media_details(request: Request, source: str, id: str):
    base_url = str(request.base_url).rstrip("/")

    # 1. NGUONC
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

    # 2. VSMOV
    elif source == "vsmov":
        try:
            from vsmov_router import extract_m3u8_url
            url = f"https://vsmov.com/api/phim/{id}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    movie = data.get("movie", {})
                    episodes = []
                    for s_idx, server in enumerate(data.get("episodes", [])):
                        server_name = server.get("server_name", f"Server #{s_idx+1}")
                        for ep in server.get("server_data", []) or server.get("items", []):
                            embed_url = ep.get("link_embed") or ep.get("embed") or ""
                            m3u8_url = ep.get("link_m3u8") or extract_m3u8_url(embed_url)
                            if m3u8_url:
                                proxied = f"{base_url}/vsmov/stream_proxy?url={urllib.parse.quote(m3u8_url, safe='')}&referer={urllib.parse.quote(embed_url or 'https://vsmov.com/', safe='')}"
                            else:
                                proxied = ""
                            episodes.append({
                                "name": f"Tập {ep.get('name', '1')} [{server_name}]",
                                "slug": ep.get("slug", ""),
                                "server": server_name,
                                "embed": embed_url,
                                "m3u8": proxied or m3u8_url
                            })
                    return {
                        "title": movie.get("name", id),
                        "original_title": movie.get("origin_name", ""),
                        "description": movie.get("content", ""),
                        "poster": movie.get("thumb_url", "") or movie.get("poster_url", ""),
                        "year": movie.get("year", "2025"),
                        "episodes": episodes
                    }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # 3. HHPANDA
    elif source == "hhpanda":
        try:
            import re
            url = f"https://hhpanda.st/{id}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://hhpanda.st/"}
            async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    html_text = res.text
                    title_m = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', html_text)
                    poster_m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html_text)
                    desc_m = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', html_text)
                    
                    title = title_m.group(1) if title_m else id
                    poster = poster_m.group(1) if poster_m else ""
                    description = desc_m.group(1) if desc_m else ""

                    ep_matches = re.findall(
                        r'data-post-id=["\'](\d+)["\'][\s\S]*?data-ep=["\']([^"\']+)["\'][\s\S]*?>(.*?)</a>',
                        html_text
                    )
                    episodes = []
                    seen_eps = set()
                    for post_id, data_ep, ep_title_raw in ep_matches:
                        ep_title = re.sub(r'<[^>]+>', '', ep_title_raw).strip()
                        key = f"{post_id}:{data_ep}"
                        if key not in seen_eps:
                            seen_eps.add(key)
                            # Player proxy or ajax resolver
                            player_url = f"{base_url}/hhpanda/player_proxy?post_id={post_id}&data_ep={data_ep}"
                            episodes.append({
                                "name": ep_title or f"Tập {data_ep}",
                                "slug": f"{post_id}_{data_ep}",
                                "server": "HHPanda 4K VIP",
                                "embed": player_url,
                                "m3u8": ""
                            })
                    return {
                        "title": title,
                        "original_title": "Hoạt Hình 3D Trung Quốc",
                        "description": description,
                        "poster": poster,
                        "year": "4K Ultra HD",
                        "episodes": episodes
                    }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # 4. MOVIESDRIVE
    elif source == "moviesdrive":
        try:
            import moviesdrive_resolver
            cands = await moviesdrive_resolver.collect_candidates(id)
            episodes = []
            for idx, cand in enumerate(cands[:12]):
                stream_res = await moviesdrive_resolver.resolve_candidate(cand)
                play_url = stream_res.get("url") if stream_res else ""
                episodes.append({
                    "name": cand.get("title", f"Option {idx+1}"),
                    "slug": f"opt_{idx+1}",
                    "server": "MoviesDrive 10Gbps",
                    "embed": "",
                    "m3u8": play_url
                })
            return {
                "title": id.replace("-", " ").title(),
                "original_title": id,
                "description": "Kho phim Hollywood / Bollywood chất lượng cao với hạ tầng CDN 10Gbps.",
                "poster": "/stremio_telegram_banner.png",
                "year": "2025",
                "episodes": episodes
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # 5. HDHUB4U
    elif source == "hdhub4u":
        try:
            import hdhub4u_resolver
            cands = await hdhub4u_resolver.collect_candidates(id)
            episodes = []
            for idx, cand in enumerate(cands[:12]):
                play_url = await hdhub4u_resolver.resolve_playable_url(cand)
                episodes.append({
                    "name": cand.get("title", f"Option {idx+1}"),
                    "slug": f"opt_{idx+1}",
                    "server": "Cloudflare R2 / FastDL",
                    "embed": "",
                    "m3u8": play_url or ""
                })
            return {
                "title": id.replace("-", " ").title(),
                "original_title": id,
                "description": "Kho phim HDHub4u Dual Audio chất lượng cao, phát mượt mà trên Stremio và Web Player.",
                "poster": "/stremio_telegram_banner.png",
                "year": "2025",
                "episodes": episodes
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # 6. TOPXX
    elif source == "topxx":
        try:
            url = f"https://topxx.vip/api/v1/movies/{id}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    payload = res.json()
                    movie = payload.get("data", {})
                    sources_list = payload.get("sources", []) or movie.get("sources", [])
                    episodes = []
                    for idx, src in enumerate(sources_list):
                        embed_code = src.get("embed_code")
                        if not embed_code and src.get("link"):
                            import re
                            m = re.search(r'/player/([a-zA-Z0-9]+)', src.get("link", ""))
                            if m: embed_code = m.group(1)
                        if embed_code:
                            direct_hls = f"https://embed.streamxx.net/backup-hls/{embed_code}/main.m3u8"
                            proxy_hls = f"{base_url}/topxx/stream_proxy?url={urllib.parse.quote(direct_hls, safe='')}&referer={urllib.parse.quote('https://embed.streamxx.net/', safe='')}"
                            web_player = f"https://embed.streamxx.net/player/{embed_code}"
                            episodes.append({
                                "name": f"HLS Stream Full HD [Server {idx+1}]",
                                "slug": f"topxx_{embed_code}",
                                "server": f"Server {idx+1}",
                                "embed": web_player,
                                "m3u8": proxy_hls
                            })
                    trans = movie.get("trans", [])
                    title = next((t.get("name") for t in trans if t.get("locale") in ["vi", "en"]), None) or id
                    return {
                        "title": title,
                        "original_title": id,
                        "description": movie.get("description", "Phim giải trí 18+ chất lượng cao"),
                        "poster": movie.get("thumbnail", ""),
                        "year": "18+ Adult",
                        "episodes": episodes
                    }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # 6. ERNAX
    elif source == "ernax":
        try:
            from ernax_router import ernax_meta_endpoint
            m_type = request.query_params.get("type", "movie")
            res = await ernax_meta_endpoint(m_type, f"ernax:{m_type}:{id}")
            meta = res.get("meta", {})
            videos = meta.get("videos", [])
            episodes = [
                {
                    "name": v.get("title", ""),
                    "slug": v.get("id", ""),
                    "server": "Ernax 4K/HLS",
                    "embed": f"{base_url}/ernax/stream/{meta.get('type', 'movie')}/{v.get('id')}.json"
                }
                for v in videos
            ] if videos else [
                {
                    "name": f"Phát {meta.get('name', id)}",
                    "slug": f"ernax_{id}",
                    "server": "Ernax 4K/HLS",
                    "embed": f"{base_url}/ernax/stream/movie/ernax:movie:{id}.json"
                }
            ]
            return {
                "title": meta.get("name", id),
                "original_title": meta.get("name", id),
                "poster": meta.get("poster", ""),
                "backdrop": meta.get("background", ""),
                "description": meta.get("description", ""),
                "genres": meta.get("genres", []),
                "year": meta.get("releaseInfo", ""),
                "quality": "4K UHD / 1080p HLS",
                "source": "Ernax Player",
                "source_id": "ernax",
                "episodes": episodes
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # 7. VIDKING
    elif source == "vidking":
        try:
            from vidking_router import vidking_meta_endpoint
            m_type = request.query_params.get("type", "movie")
            res = await vidking_meta_endpoint(m_type, f"vidking:{m_type}:{id}")
            meta = res.get("meta", {})
            videos = meta.get("videos", [])
            episodes = [
                {
                    "name": v.get("title", ""),
                    "slug": v.get("id", ""),
                    "server": "Vidking Multi-Server",
                    "embed": f"{base_url}/vidking/stream/{meta.get('type', 'movie')}/{v.get('id')}.json"
                }
                for v in videos
            ] if videos else [
                {
                    "name": f"Phát {meta.get('name', id)}",
                    "slug": f"vidking_{id}",
                    "server": "Vidking Multi-Server",
                    "embed": f"{base_url}/vidking/stream/movie/vidking:movie:{id}.json"
                }
            ]
            return {
                "title": meta.get("name", id),
                "original_title": meta.get("name", id),
                "poster": meta.get("poster", ""),
                "backdrop": meta.get("background", ""),
                "description": meta.get("description", ""),
                "genres": meta.get("genres", []),
                "year": meta.get("releaseInfo", ""),
                "quality": "4K UHD / 1080p HLS",
                "source": "Vidking Player",
                "source_id": "vidking",
                "episodes": episodes
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # 8. HDTODAY
    elif source == "hdtoday":
        try:
            from hdtoday_router import hdtoday_meta_handler
            m_type = "series" if "tv" in id else "movie"
            res = await hdtoday_meta_handler(m_type, f"hdtoday:{m_type}:{id}")
            meta = res.get("meta", {})
            return {
                "title": meta.get("name", id),
                "original_title": meta.get("name", id),
                "poster": meta.get("poster", ""),
                "backdrop": meta.get("background", ""),
                "description": meta.get("description", ""),
                "genres": meta.get("genres", []),
                "year": meta.get("releaseInfo", ""),
                "quality": "Full HD / HLS",
                "source": "HDToday Cinema",
                "source_id": "hdtoday",
                "episodes": [
                    {
                        "name": v.get("title", ""),
                        "slug": v.get("id", ""),
                        "server": "HDToday HLS",
                        "embed": f"{base_url}/hdtoday/stream/{meta.get('type', 'movie')}/{v.get('id')}.json"
                    }
                    for v in meta.get("videos", [])
                ]
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # 8. TELEGRAM
    elif source == "telegram":
        try:
            parts = id.split(":")
            chat_id = parts[0] if len(parts) > 1 else str(Config.TELEGRAM_CHANNEL_ID)
            msg_id = parts[1] if len(parts) > 1 else parts[0]
            stream_url = f"{base_url}/stream?id={chat_id}:{msg_id}"
            return {
                "title": f"Telegram Media #{msg_id}",
                "original_title": f"Chat {chat_id} Msg {msg_id}",
                "description": "Phát video trực tiếp từ Telegram Vault với hỗ trợ Range Request và giải mã mượt mà.",
                "poster": "/stremio_telegram_banner.png",
                "year": "Telegram Vault",
                "episodes": [
                    {
                        "name": f"Phát Trực Tiếp Tập #{msg_id}",
                        "slug": f"tg_{msg_id}",
                        "server": "Telegram Debrid Engine",
                        "embed": "",
                        "m3u8": stream_url
                    }
                ]
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=404, detail=f"Source {source} detail handler not implemented")


@dashboard_router.get("/dashboard", response_class=HTMLResponse)
@dashboard_router.get("/admin", response_class=HTMLResponse)
async def dashboard_ui(request: Request):
    if is_auth_required() and not is_authenticated(request):
        return RedirectResponse(url="/login?redirect=/dashboard", status_code=302)
    html = r"""<!DOCTYPE html>
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

        .addon-card.card-disabled {
            opacity: 0.65;
            border-color: rgba(239, 68, 68, 0.25);
            background: rgba(20, 20, 24, 0.7);
        }

        .addon-card.card-disabled:hover {
            opacity: 0.9;
            border-color: rgba(239, 68, 68, 0.45);
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

        /* Switch Toggle Component */
        .switch {
            position: relative;
            display: inline-block;
            width: 44px;
            height: 24px;
            flex-shrink: 0;
        }

        .switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }

        .slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: #27272a;
            border: 1px solid #3f3f46;
            transition: .3s ease;
            border-radius: 24px;
        }

        .slider:before {
            position: absolute;
            content: "";
            height: 16px;
            width: 16px;
            left: 3px;
            bottom: 3px;
            background-color: #a1a1aa;
            transition: .3s ease;
            border-radius: 50%;
        }

        input:checked + .slider {
            background-color: var(--primary);
            border-color: var(--primary);
            box-shadow: 0 0 12px rgba(99, 102, 241, 0.45);
        }

        input:checked + .slider:before {
            transform: translateX(20px);
            background-color: #ffffff;
        }

        .config-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            padding: 12px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .config-row:last-child {
            border-bottom: none;
            padding-bottom: 0;
        }

        .config-label h5 {
            font-size: 13.5px;
            font-weight: 700;
            color: #fff;
            margin-bottom: 2px;
        }

        .config-label p {
            font-size: 12px;
            color: var(--text-dim);
            line-height: 1.4;
        }

        /* Logs Console & Toolbar */
        .log-toolbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 12px;
            background: var(--bg-card);
            padding: 12px 18px;
            border-radius: var(--radius-md);
            border: 1px solid var(--border-color);
        }

        .filter-btn-group {
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
        }

        .btn-filter {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            color: var(--text-muted);
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 11.5px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s ease;
            display: inline-flex;
            align-items: center;
            gap: 5px;
        }

        .btn-filter:hover {
            color: #fff;
            border-color: #52525b;
        }

        .btn-filter.active {
            background: var(--primary-light);
            color: var(--primary);
            border-color: var(--border-accent);
            box-shadow: 0 0 10px rgba(99, 102, 241, 0.2);
        }

        .btn-filter.filter-info.active {
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
            border-color: rgba(56, 189, 248, 0.4);
            box-shadow: 0 0 10px rgba(56, 189, 248, 0.2);
        }

        .btn-filter.filter-warning.active {
            background: rgba(251, 191, 36, 0.15);
            color: #fbbf24;
            border-color: rgba(251, 191, 36, 0.4);
            box-shadow: 0 0 10px rgba(251, 191, 36, 0.2);
        }

        .btn-filter.filter-error.active {
            background: rgba(239, 68, 68, 0.2);
            color: #f87171;
            border-color: rgba(239, 68, 68, 0.4);
            box-shadow: 0 0 10px rgba(239, 68, 68, 0.25);
        }

        .btn-filter.filter-debug.active {
            background: rgba(168, 85, 247, 0.15);
            color: #c084fc;
            border-color: rgba(168, 85, 247, 0.4);
            box-shadow: 0 0 10px rgba(168, 85, 247, 0.2);
        }

        .log-console {
            background: #08080c;
            border: 1px solid #27272a;
            border-radius: var(--radius-lg);
            padding: 12px;
            font-family: 'Fira Code', 'JetBrains Mono', Consolas, monospace;
            font-size: 12px;
            color: #e4e4e7;
            height: 540px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 4px;
            box-shadow: inset 0 2px 14px rgba(0, 0, 0, 0.8);
            scroll-behavior: smooth;
        }

        /* Log Line Base & Level-specific Row Colors */
        .log-line {
            display: flex;
            align-items: flex-start;
            gap: 8px;
            line-height: 1.55;
            padding: 5px 10px;
            border-radius: 6px;
            border-left: 3.5px solid #3f3f46;
            background: rgba(255, 255, 255, 0.015);
            transition: background 0.15s ease, border-left-color 0.15s ease;
        }

        .log-line:hover {
            background: rgba(255, 255, 255, 0.05);
        }

        /* Row Tint by Severity Level */
        .log-row-INFO {
            border-left-color: #0284c7;
            background: rgba(2, 132, 199, 0.04);
        }
        .log-row-INFO:hover {
            background: rgba(2, 132, 199, 0.09);
        }

        .log-row-WARNING {
            border-left-color: #f59e0b;
            background: rgba(245, 158, 11, 0.08);
        }
        .log-row-WARNING:hover {
            background: rgba(245, 158, 11, 0.14);
        }
        .log-row-WARNING .log-msg-text {
            color: #fef08a;
        }

        .log-row-ERROR, .log-row-CRITICAL {
            border-left-color: #ef4444;
            background: rgba(239, 68, 68, 0.1);
            box-shadow: inset 0 0 12px rgba(239, 68, 68, 0.04);
        }
        .log-row-ERROR:hover, .log-row-CRITICAL:hover {
            background: rgba(239, 68, 68, 0.18);
        }
        .log-row-ERROR .log-msg-text, .log-row-CRITICAL .log-msg-text {
            color: #fecaca;
        }

        .log-row-DEBUG {
            border-left-color: #8b5cf6;
            background: rgba(139, 92, 246, 0.03);
        }
        .log-row-DEBUG:hover {
            background: rgba(139, 92, 246, 0.08);
        }
        .log-row-DEBUG .log-msg-text {
            color: #d8b4fe;
        }

        .log-idx {
            color: #52525b;
            font-size: 11px;
            font-weight: 500;
            min-width: 22px;
            flex-shrink: 0;
            text-align: right;
            user-select: none;
            margin-top: 1px;
        }

        .log-time {
            color: #94a3b8;
            font-size: 11.5px;
            font-weight: 500;
            flex-shrink: 0;
            user-select: none;
            margin-top: 1px;
            letter-spacing: 0.3px;
        }

        /* Level Badges */
        .log-badge-level {
            font-size: 9.5px;
            font-weight: 800;
            padding: 1px 6px;
            border-radius: 4px;
            letter-spacing: 0.5px;
            flex-shrink: 0;
            text-transform: uppercase;
            margin-top: 1px;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }

        .log-lvl-INFO {
            background: rgba(56, 189, 248, 0.18);
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.35);
        }

        .log-lvl-WARNING {
            background: rgba(251, 191, 36, 0.22);
            color: #fbbf24;
            border: 1px solid rgba(251, 191, 36, 0.55);
            font-weight: 800;
        }

        .log-lvl-ERROR, .log-lvl-CRITICAL {
            background: rgba(239, 68, 68, 0.25);
            color: #fca5a5;
            border: 1px solid rgba(239, 68, 68, 0.6);
            box-shadow: 0 0 8px rgba(239, 68, 68, 0.3);
            font-weight: 800;
        }

        .log-lvl-DEBUG {
            background: rgba(192, 132, 252, 0.18);
            color: #d8b4fe;
            border: 1px solid rgba(192, 132, 252, 0.35);
        }

        /* Module-specific Badges */
        .log-badge-module {
            font-size: 10px;
            font-weight: 700;
            padding: 1px 7px;
            border-radius: 4px;
            flex-shrink: 0;
            margin-top: 1px;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }

        .mod-nguonc {
            background: rgba(16, 185, 129, 0.18);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.35);
        }
        .mod-vsmov {
            background: rgba(59, 130, 246, 0.18);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.35);
        }
        .mod-hhpanda {
            background: rgba(245, 158, 11, 0.18);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.35);
        }
        .mod-moviesdrive {
            background: rgba(168, 85, 247, 0.18);
            color: #c084fc;
            border: 1px solid rgba(168, 85, 247, 0.35);
        }
        .mod-hdhub4u {
            background: rgba(244, 63, 94, 0.18);
            color: #fb7185;
            border: 1px solid rgba(244, 63, 94, 0.35);
        }
        .mod-topxx {
            background: rgba(239, 68, 68, 0.18);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.35);
        }
        .mod-iptv {
            background: rgba(6, 182, 212, 0.18);
            color: #22d3ee;
            border: 1px solid rgba(6, 182, 212, 0.35);
        }
        .mod-film4k {
            background: rgba(16, 185, 129, 0.18);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.35);
        }
        .mod-telegram, .mod-tg_client {
            background: rgba(6, 182, 212, 0.18);
            color: #22d3ee;
            border: 1px solid rgba(6, 182, 212, 0.35);
        }
        .mod-debrid {
            background: rgba(234, 179, 8, 0.18);
            color: #fde047;
            border: 1px solid rgba(234, 179, 8, 0.35);
        }
        .mod-subtitles, .mod-sync_vtt, .mod-translation, .mod-tts {
            background: rgba(236, 72, 153, 0.18);
            color: #f472b6;
            border: 1px solid rgba(236, 72, 153, 0.35);
        }
        .mod-uvicorn, .mod-fastapi {
            background: rgba(148, 163, 184, 0.15);
            color: #cbd5e1;
            border: 1px solid rgba(148, 163, 184, 0.3);
        }
        .mod-addon, .mod-dashboard, .mod-default {
            background: rgba(99, 102, 241, 0.18);
            color: #a5b4fc;
            border: 1px solid rgba(99, 102, 241, 0.35);
        }

        .log-msg-text {
            flex: 1;
            color: #e4e4e7;
            word-break: break-all;
            line-height: 1.5;
        }

        /* Message Syntax Highlights */
        .code-success { color: #34d399; font-weight: 700; }
        .code-warning { color: #fbbf24; font-weight: 700; }
        .code-danger { color: #f87171; font-weight: 700; }
        
        .code-method-get { color: #38bdf8; font-weight: 800; }
        .code-method-post { color: #34d399; font-weight: 800; }
        .code-method-opt { color: #c084fc; font-weight: 800; }
        .code-method-del { color: #fb7185; font-weight: 800; }

        .code-ip { color: #fde047; font-weight: 600; }
        .code-url { color: #38bdf8; text-decoration: underline; text-underline-offset: 2px; }
        .code-route { color: #c4b5fd; font-weight: 600; }
        .code-file { color: #fdba74; font-weight: 600; }
        .code-metric { color: #2dd4bf; font-weight: 600; }
        .font-bold { font-weight: 700; }

        .log-highlight {
            background: #fde047;
            color: #000;
            padding: 0 4px;
            border-radius: 2px;
            font-weight: 700;
        }

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
                        <span class="nav-badge">12 Addons</span>
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
                <li>
                    <a class="nav-item" onclick="handleLogout()" style="color: #f87171;">
                        <i class="fa-solid fa-arrow-right-from-bracket"></i>
                        <span>Đăng Xuất</span>
                    </a>
                </li>
            </ul>

            <div class="sidebar-footer">
                <div class="status-pill">
                    <span class="status-dot"></span>
                    <span id="sidebarStatusText">Máy chủ Online</span>
                </div>
                <a href="/login" class="btn btn-secondary btn-sm" title="Trang đăng nhập">
                    <i class="fa-solid fa-lock"></i>
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
                    <button class="btn btn-secondary btn-sm" onclick="handleLogout()" title="Đăng xuất khỏi Dashboard">
                        <i class="fa-solid fa-arrow-right-from-bracket" style="color: #f87171;"></i> Đăng Xuất
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
                                <h3 id="statUptime">0h 0m</h3>
                            </div>
                        </div>

                        <div class="stat-card" style="--card-color: var(--cyan);">
                            <div class="stat-icon-wrapper">
                                <i class="fa-solid fa-globe"></i>
                            </div>
                            <div class="stat-info">
                                <h4 id="statNetworkTitle">Tên Miền / Địa Chỉ IP</h4>
                                <h3 id="statLanIp" style="font-size: 14px; word-break: break-all;">Đang tải...</h3>
                            </div>
                        </div>

                        <div class="stat-card" style="--card-color: var(--accent);">
                            <div class="stat-icon-wrapper">
                                <i class="fa-brands fa-telegram"></i>
                            </div>
                            <div class="stat-info">
                                <h4>Telegram Vault</h4>
                                <h3 id="statTelegram">Đang kết nối...</h3>
                            </div>
                        </div>

                        <div class="stat-card" style="--card-color: var(--warning);">
                            <div class="stat-icon-wrapper">
                                <i class="fa-solid fa-database"></i>
                            </div>
                            <div class="stat-info">
                                <h4>Bộ Nhớ Đệm</h4>
                                <h3 id="statCacheEntries">0 mục</h3>
                            </div>
                        </div>
                    </div>

                    <!-- Quick Addons Overview -->
                    <div class="addons-section">
                        <div class="section-header">
                            <div class="section-title">
                                <h3>🧩 Nguồn Phim & Addon Đang Hoạt Động</h3>
                                <p>Cài đặt nhanh các nguồn addon trực tiếp vào Stremio với 1 cú nhấp chuột.</p>
                            </div>
                            <button class="btn btn-primary btn-sm" onclick="switchTab('addons')">
                                <i class="fa-solid fa-arrow-right"></i> Xem tất cả Addon
                            </button>
                        </div>
                        <div class="addons-grid" id="overviewAddonsGrid">
                            <!-- Loaded dynamically -->
                        </div>
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
                                <option value="public" selected>🌐 Tên miền Public / Domain (Khuyên dùng)</option>
                                <option value="lan">📱 Mạng LAN (Android TV / Cùng Wi-Fi)</option>
                                <option value="local">💻 Máy tính cục bộ (127.0.0.1)</option>
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
                            <input type="text" id="searchInput" class="search-input" placeholder="Nhập tên phim cần tìm (ví dụ: Tiên Nghịch, Spider-man, Avatar, Thợ Săn, House of the Dragon...)" onkeydown="if(event.key==='Enter') executeSearch()">
                            <select id="searchSourceSelect" class="source-select">
                                <option value="all">🌐 Tất cả nguồn (Universal Search)</option>
                                <option value="nguonc">🎬 NguonC Cinema (Phim Lẻ & Phim Bộ)</option>
                                <option value="vsmov">🍿 VSMov Cinema (Tổng hợp Phim & Series)</option>
                                <option value="hhpanda">🐉 HHPanda 3D (Hoạt Hình 3D 4K)</option>
                                <option value="moviesdrive">🎥 MoviesDrive (Bollywood & Hollywood)</option>
                                <option value="hdhub4u">⚡ HDHub4u (Fast 10Gbps CDN)</option>
                                <option value="topxx">🔞 TopXX Cinema (Adult 18+)</option>
                                <option value="telegram">📦 Telegram Media Vault (Kho Riêng)</option>
                            </select>
                            <button class="btn btn-primary" onclick="executeSearch()">
                                <i class="fa-solid fa-magnifying-glass"></i> Tìm kiếm
                            </button>
                        </div>
                    </div>

                    <div id="searchResultsContainer">
                        <p style="color: var(--text-dim); text-align: center; padding: 40px;">Hãy nhập từ khóa để tìm kiếm phim trên tất cả 7 nguồn dữ liệu...</p>
                    </div>
                </div>

                <!-- TAB 4: Services & Config -->
                <div class="tab-pane" id="tab-services">
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 20px;">
                        
                        <!-- CARD 1: Subtitle & AI Translation Config -->
                        <div class="stat-card" style="flex-direction: column; align-items: stretch; gap: 16px;">
                            <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border-color); padding-bottom: 10px;">
                                <h4 style="font-size: 15px; color: #fff; font-family: var(--font-heading); font-weight: 700; display: flex; align-items: center; gap: 8px;">
                                    <i class="fa-solid fa-closed-captioning" style="color: var(--primary);"></i> Cấu Hình Phụ Đề & AI VietSub
                                </h4>
                                <span class="nav-badge" style="background: rgba(99, 102, 241, 0.2); color: var(--primary); border: 1px solid var(--border-accent);">Real-time</span>
                            </div>
                            
                            <div class="config-row" style="background: rgba(99, 102, 241, 0.08); border: 1px solid rgba(99, 102, 241, 0.25); border-radius: var(--radius-sm); padding: 12px; margin-bottom: 4px;">
                                <div class="config-label">
                                    <h5 style="color: #fff; font-weight: 700; display: flex; align-items: center; gap: 6px;">
                                        <i class="fa-solid fa-power-off" style="color: var(--primary);"></i> Tính Năng Phụ Đề (Subtitles Feature)
                                    </h5>
                                    <p style="color: #cbd5e1;">Bật hoặc tắt toàn bộ tài nguyên phụ đề Stremio (OpenSubtitles, trích xuất sub video & AI VietSub tracks).</p>
                                </div>
                                <label class="switch">
                                    <input type="checkbox" id="chkEnableSubtitles" onchange="toggleConfigFeature('enable_subtitles', this.checked, 'Tính Năng Phụ Đề')">
                                    <span class="slider"></span>
                                </label>
                            </div>

                            <div class="config-row">
                                <div class="config-label">
                                    <h5>🌐 Tự Động Dịch Phụ Đề (Auto VietSub)</h5>
                                    <p>Tự động trích xuất phụ đề và dịch sang Tiếng Việt bằng AI khi phát video.</p>
                                </div>
                                <label class="switch">
                                    <input type="checkbox" id="chkAutoVietsub" onchange="toggleConfigFeature('auto_vietsub', this.checked, 'Tự Động Dịch Sub')">
                                    <span class="slider"></span>
                                </label>
                            </div>

                            <div class="config-row">
                                <div class="config-label">
                                    <h5>🎙️ Thuyết Minh Tự Động (Auto Voiceover TTS)</h5>
                                    <p>Tự động lồng tiếng đọc phụ đề Tiếng Việt song song với luồng âm thanh gốc.</p>
                                </div>
                                <label class="switch">
                                    <input type="checkbox" id="chkAutoThuyetMinh" onchange="toggleConfigFeature('auto_thuyet_minh', this.checked, 'Thuyết Minh AI')">
                                    <span class="slider"></span>
                                </label>
                            </div>

                            <div class="config-row">
                                <div class="config-label">
                                    <h5>🤖 Dịch Qua Gemini AI</h5>
                                    <p id="descGeminiModel">Mô hình: Gemini AI API / Flash</p>
                                </div>
                                <label class="switch">
                                    <input type="checkbox" id="chkEnableGemini" onchange="toggleConfigFeature('enable_gemini', this.checked, 'Dịch Gemini AI')">
                                    <span class="slider"></span>
                                </label>
                            </div>

                            <div class="config-row">
                                <div class="config-label">
                                    <h5>✨ Dịch Qua Custom AI API</h5>
                                    <p id="descCustomAiModel">Mô hình: Custom LLM API Model</p>
                                </div>
                                <label class="switch">
                                    <input type="checkbox" id="chkEnableCustomAi" onchange="toggleConfigFeature('enable_custom_ai', this.checked, 'Dịch Custom AI')">
                                    <span class="slider"></span>
                                </label>
                            </div>

                            <div class="config-row" style="border-bottom: none;">
                                <div class="config-label">
                                    <h5>⏱️ Độ Lệch Thời Gian Sub (+/- Giây)</h5>
                                    <p>Chỉnh sub hiện sớm (-) hoặc trễ (+) để khớp âm thanh.</p>
                                </div>
                                <div style="display: flex; align-items: center; gap: 6px;">
                                    <input type="number" id="inputSubOffset" step="0.5" style="width: 70px; background: var(--bg-body); border: 1px solid #3f3f46; border-radius: var(--radius-sm); padding: 5px 8px; font-size: 12px; color: #fff; text-align: center;" value="0.0">
                                    <button class="btn btn-secondary btn-sm" onclick="saveSubtitleOffset()"><i class="fa-solid fa-floppy-disk"></i> Lưu</button>
                                </div>
                            </div>
                        </div>

                        <!-- CARD 2: Telegram Storage & Upload -->
                        <div class="stat-card" style="flex-direction: column; align-items: stretch; gap: 16px;">
                            <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border-color); padding-bottom: 10px;">
                                <h4 style="font-size: 15px; color: #fff; font-family: var(--font-heading); font-weight: 700; display: flex; align-items: center; gap: 8px;">
                                    <i class="fa-brands fa-telegram" style="color: var(--cyan);"></i> Telegram Media Vault
                                </h4>
                            </div>

                            <div class="config-row">
                                <div class="config-label">
                                    <h5>☁️ Tự Động Lưu Phim Vào Kênh</h5>
                                    <p>Tự động tải các stream Debrid / Torrent về kênh Telegram riêng tư.</p>
                                </div>
                                <label class="switch">
                                    <input type="checkbox" id="chkAutoUpload" onchange="toggleConfigFeature('auto_upload', this.checked, 'Tự Động Upload Telegram')">
                                    <span class="slider"></span>
                                </label>
                            </div>

                            <div style="font-size: 12.5px; color: var(--text-muted); line-height: 1.8; margin-top: 8px; background: rgba(255, 255, 255, 0.02); padding: 12px; border-radius: var(--radius-sm); border: 1px solid rgba(255, 255, 255, 0.05);">
                                <p>• <strong>Channel ID</strong>: <span id="cfgTgChannel" style="color: var(--cyan); font-family: var(--font-mono);">Đang tải...</span></p>
                                <p>• <strong>User Session</strong>: <span id="cfgTgSession">Đang tải...</span></p>
                                <p>• <strong>Bot Token</strong>: <span id="cfgTgBot">Đang tải...</span></p>
                            </div>
                        </div>

                        <!-- CARD 3: Admin Security & Password -->
                        <div class="stat-card" style="flex-direction: column; align-items: stretch; gap: 16px;">
                            <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border-color); padding-bottom: 10px;">
                                <h4 style="font-size: 15px; color: #fff; font-family: var(--font-heading); font-weight: 700; display: flex; align-items: center; gap: 8px;">
                                    <i class="fa-solid fa-shield-halved" style="color: var(--warning);"></i> Bảo Mật & Mật Khẩu Quản Trị
                                </h4>
                                <span id="badgeAuthStatus" class="nav-badge" style="background: rgba(245, 158, 11, 0.15); color: var(--warning); border: 1px solid rgba(245, 158, 11, 0.3);">Kiểm tra...</span>
                            </div>

                            <div style="display: flex; flex-direction: column; gap: 12px;">
                                <div class="config-row">
                                    <div class="config-label">
                                        <h5>Tên đăng nhập (Username)</h5>
                                        <p>Tên tài khoản quản trị Dashboard.</p>
                                    </div>
                                    <input type="text" id="inputAdminUser" style="width: 140px; background: var(--bg-body); border: 1px solid #3f3f46; border-radius: var(--radius-sm); padding: 5px 8px; font-size: 12px; color: #fff;" placeholder="admin">
                                </div>

                                <div class="config-row" style="border-bottom: none;">
                                    <div class="config-label">
                                        <h5>Mật khẩu quản trị</h5>
                                        <p>Mật khẩu bảo vệ trang Dashboard.</p>
                                    </div>
                                    <div style="display: flex; align-items: center; gap: 6px;">
                                        <input type="password" id="inputAdminPass" style="width: 140px; background: var(--bg-body); border: 1px solid #3f3f46; border-radius: var(--radius-sm); padding: 5px 8px; font-size: 12px; color: #fff;" placeholder="Mật khẩu mới...">
                                        <button class="btn btn-primary btn-sm" onclick="saveAdminCredentials()"><i class="fa-solid fa-key"></i> Đổi MK</button>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- CARD 4: Debrid & Other Services -->
                        <div class="stat-card" style="flex-direction: column; align-items: stretch; gap: 16px;">
                            <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border-color); padding-bottom: 10px;">
                                <h4 style="font-size: 15px; color: #fff; font-family: var(--font-heading); font-weight: 700; display: flex; align-items: center; gap: 8px;">
                                    <i class="fa-solid fa-server" style="color: var(--success);"></i> Hạ Tầng & Dịch Vụ Debrid
                                </h4>
                            </div>

                            <div style="font-size: 12.5px; color: var(--text-muted); line-height: 1.8; background: rgba(255, 255, 255, 0.02); padding: 12px; border-radius: var(--radius-sm); border: 1px solid rgba(255, 255, 255, 0.05);">
                                <p>• <strong>Real-Debrid</strong>: <span id="cfgRdStatus">Đang kiểm tra...</span></p>
                                <p>• <strong>TorBox Debrid</strong>: <span id="cfgTorboxStatus">Đang kiểm tra...</span></p>
                                <p>• <strong>qBittorrent WebUI</strong>: <span id="cfgQbitStatus">Đang kiểm tra...</span></p>
                                <p>• <strong>Gemini API Status</strong>: <span id="cfgGeminiStatus">Đang kiểm tra...</span></p>
                            </div>
                        </div>

                    </div>
                </div>

                <!-- TAB 5: Logs & Cache -->
                <div class="tab-pane" id="tab-logs">
                    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
                        <div>
                            <h3 style="font-family: var(--font-heading); font-size: 18px; font-weight: 700;">📜 Nhật Ký Hoạt Động Thời Gian Thực</h3>
                            <p style="font-size: 13px; color: var(--text-dim);">Theo dõi trực quan các sự kiện, mã HTTP, luồng stream và phát hiện lỗi với màu sắc nổi bật.</p>
                        </div>
                        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                            <button class="btn btn-secondary btn-sm" onclick="copyLogs()">
                                <i class="fa-solid fa-copy"></i> Sao Chép
                            </button>
                            <button class="btn btn-secondary btn-sm" onclick="clearConsoleDisplay()">
                                <i class="fa-solid fa-eraser"></i> Xóa Màn Hình
                            </button>
                            <button class="btn btn-danger btn-sm" onclick="clearSystemCache()">
                                <i class="fa-solid fa-trash"></i> Xóa Cache
                            </button>
                            <button class="btn btn-secondary btn-sm" id="btnLogPause" onclick="toggleLogPause()">
                                <i class="fa-solid fa-pause"></i> Tạm Dừng
                            </button>
                            <button class="btn btn-primary btn-sm" onclick="fetchLogs()">
                                <i class="fa-solid fa-arrows-rotate"></i> Làm mới
                            </button>
                        </div>
                    </div>

                    <!-- Log Filters & Search Toolbar -->
                    <div class="log-toolbar">
                        <div class="filter-btn-group">
                            <button class="btn-filter active" onclick="setLogLevelFilter('ALL', this)"><i class="fa-solid fa-list-ul"></i> Tất cả (<span id="countAll">0</span>)</button>
                            <button class="btn-filter filter-info" onclick="setLogLevelFilter('INFO', this)"><i class="fa-solid fa-circle-info"></i> INFO (<span id="countInfo">0</span>)</button>
                            <button class="btn-filter filter-warning" onclick="setLogLevelFilter('WARNING', this)"><i class="fa-solid fa-triangle-exclamation"></i> WARN (<span id="countWarn">0</span>)</button>
                            <button class="btn-filter filter-error" onclick="setLogLevelFilter('ERROR', this)"><i class="fa-solid fa-circle-xmark"></i> ERROR (<span id="countErr">0</span>)</button>
                            <button class="btn-filter filter-debug" onclick="setLogLevelFilter('DEBUG', this)"><i class="fa-solid fa-bug"></i> DEBUG (<span id="countDebug">0</span>)</button>
                        </div>

                        <div style="display: flex; align-items: center; gap: 12px; flex: 1; max-width: 400px;">
                            <div style="position: relative; flex: 1;">
                                <input type="text" id="logSearchInput" placeholder="Lọc từ khóa log (GET, 200, m3u8, nguonc...)" oninput="filterAndRenderLogs()" style="width: 100%; background: var(--bg-body); border: 1px solid #3f3f46; border-radius: var(--radius-sm); padding: 6px 10px 6px 28px; font-size: 12px; color: #fff; outline: none;">
                                <i class="fa-solid fa-filter" style="position: absolute; left: 9px; top: 8px; font-size: 11px; color: var(--text-dim);"></i>
                            </div>
                        </div>

                        <div style="display: flex; align-items: center; gap: 14px;">
                            <label style="font-size: 12px; color: var(--text-muted); display: flex; align-items: center; gap: 6px; cursor: pointer;">
                                <input type="checkbox" id="chkAutoScroll" checked> Tự cuộn xuống
                            </label>
                            <span class="status-pill" style="font-size: 11px;">
                                <span class="status-dot"></span> Live Stream (2s)
                            </span>
                        </div>
                    </div>

                    <div class="log-console" id="logConsole">
                        <div class="log-line"><span class="log-time">--:--:--</span><span class="log-msg-text">Đang kết nối nhật ký máy chủ...</span></div>
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
                    <iframe id="iframeVideoPlayer" class="video-player" style="display:none; width:100%; height:100%; position:absolute; top:0; left:0; border:none;" allow="autoplay; fullscreen; encrypted-media" allowfullscreen></iframe>
                </div>
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    <h4 style="font-size: 13px; font-weight: 700; color: var(--text-muted);">Danh sách tập / Luồng phát:</h4>
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
                if (data.configured_url && !data.configured_url.includes('localhost') && !data.configured_url.includes('127.0.0.1')) {
                    document.getElementById('statNetworkTitle').textContent = '🌐 Tên Miền Addon';
                    document.getElementById('statLanIp').textContent = data.configured_url;
                } else {
                    document.getElementById('statNetworkTitle').textContent = '📱 Địa Chỉ LAN IP';
                    document.getElementById('statLanIp').textContent = `${data.lan_ip}:${data.port}`;
                }
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

                // Update interactive switches
                const chkSub = document.getElementById('chkEnableSubtitles');
                if (chkSub) chkSub.checked = data.services.enable_subtitles !== false;

                const chkVietsub = document.getElementById('chkAutoVietsub');
                if (chkVietsub) chkVietsub.checked = !!data.services.auto_vietsub;

                const chkThuyetMinh = document.getElementById('chkAutoThuyetMinh');
                if (chkThuyetMinh) chkThuyetMinh.checked = !!data.services.auto_thuyet_minh;

                const chkGemini = document.getElementById('chkEnableGemini');
                if (chkGemini) chkGemini.checked = !!data.services.enable_gemini;

                const chkCustomAi = document.getElementById('chkEnableCustomAi');
                if (chkCustomAi) chkCustomAi.checked = !!data.services.enable_custom_ai;

                const chkUpload = document.getElementById('chkAutoUpload');
                if (chkUpload) chkUpload.checked = !!data.services.auto_upload;

                const inputOffset = document.getElementById('inputSubOffset');
                if (inputOffset && data.services.subtitle_offset !== undefined) {
                    inputOffset.value = data.services.subtitle_offset;
                }

                const descGemini = document.getElementById('descGeminiModel');
                if (descGemini && data.services.gemini_model) {
                    descGemini.textContent = `Mô hình: ${data.services.gemini_model} / Gemini API`;
                }

                const descCustom = document.getElementById('descCustomAiModel');
                if (descCustom && data.services.custom_ai_model) {
                    descCustom.textContent = `Mô hình: ${data.services.custom_ai_model} / Custom API`;
                }

                // Auth status update
                if (data.auth) {
                    const badge = document.getElementById('badgeAuthStatus');
                    if (badge) {
                        if (data.auth.has_password) {
                            badge.textContent = '🔒 Đã Bật Mật Khẩu';
                            badge.style.color = 'var(--success)';
                            badge.style.background = 'rgba(16, 185, 129, 0.15)';
                            badge.style.borderColor = 'rgba(16, 185, 129, 0.3)';
                        } else {
                            badge.textContent = '🔓 Chưa Đặt Mật Khẩu';
                            badge.style.color = 'var(--warning)';
                            badge.style.background = 'rgba(245, 158, 11, 0.15)';
                            badge.style.borderColor = 'rgba(245, 158, 11, 0.3)';
                        }
                    }
                    const userInput = document.getElementById('inputAdminUser');
                    if (userInput && data.auth.username) userInput.value = data.auth.username;
                }

            } catch (err) {
                console.error('Fetch status failed', err);
            }
        }

        async function handleLogout() {
            if (confirm("Bạn có chắc chắn muốn đăng xuất khỏi Dashboard?")) {
                try {
                    await fetch('/api/auth/logout', { method: 'POST' });
                    window.location.href = '/login';
                } catch {
                    window.location.href = '/logout';
                }
            }
        }

        async function saveAdminCredentials() {
            const user = document.getElementById('inputAdminUser')?.value.trim() || 'admin';
            const pass = document.getElementById('inputAdminPass')?.value || '';
            if (!pass) {
                showToast('Vui lòng nhập mật khẩu mới!', 'fa-triangle-exclamation');
                return;
            }
            try {
                const res = await fetch('/api/config/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ admin_username: user, admin_password: pass })
                });
                const data = await res.json();
                if (data.success) {
                    showToast('Đã cập nhật mật khẩu quản trị thành công!', 'fa-shield-halved');
                    document.getElementById('inputAdminPass').value = '';
                    fetchSystemStatus();
                }
            } catch (err) {
                showToast('Lỗi: ' + err.message, 'fa-triangle-exclamation');
            }
        }

        async function toggleConfigFeature(key, enabled, label) {
            try {
                const res = await fetch('/api/config/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ [key]: enabled })
                });
                const data = await res.json();
                if (data.success) {
                    showToast(`${enabled ? 'Đã BẬT' : 'Đã TẮT'} ${label}!`, enabled ? 'fa-toggle-on' : 'fa-toggle-off');
                    fetchSystemStatus();
                    if (key === 'enable_subtitles') {
                        fetchAddons();
                    }
                } else {
                    showToast('Lỗi khi cập nhật cấu hình', 'fa-triangle-exclamation');
                }
            } catch (err) {
                showToast(`Lỗi: ${err.message}`, 'fa-triangle-exclamation');
            }
        }

        async function saveSubtitleOffset() {
            const offset = parseFloat(document.getElementById('inputSubOffset')?.value || '0');
            try {
                const res = await fetch('/api/config/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ subtitle_offset: offset })
                });
                const data = await res.json();
                if (data.success) {
                    showToast(`Đã lưu độ lệch sub: ${offset >= 0 ? '+' : ''}${offset}s!`, 'fa-clock');
                }
            } catch (err) {
                showToast(`Lỗi: ${err.message}`, 'fa-triangle-exclamation');
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

        async function toggleMovieSource(sourceId, isEnabled, sourceName) {
            const configKey = (sourceId === 'subtitles' || sourceId === 'subtitle') ? 'enable_subtitles' : `enable_source_${sourceId.replace('_debrid', '')}`;
            try {
                const res = await fetch('/api/config/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ [configKey]: isEnabled })
                });
                const data = await res.json();
                if (data.success) {
                    showToast(`${isEnabled ? 'Đã BẬT' : 'Đã TẮT'} ${sourceName}!`, isEnabled ? 'fa-toggle-on' : 'fa-toggle-off');
                    fetchAddons();
                    fetchSystemStatus();
                } else {
                    showToast('Lỗi khi cập nhật trạng thái nguồn', 'fa-triangle-exclamation');
                }
            } catch (err) {
                showToast('Lỗi: ' + err.message, 'fa-triangle-exclamation');
            }
        }

        async function toggleBoardDisplay(sourceId, isBoardEnabled, sourceName) {
            const configKey = `enable_board_${sourceId.replace('_debrid', '')}`;
            try {
                const res = await fetch('/api/config/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ [configKey]: isBoardEnabled })
                });
                const data = await res.json();
                if (data.success) {
                    showToast(
                        isBoardEnabled 
                            ? `Đã BẬT ${sourceName} ra Màn hình chính (Board)!` 
                            : `Đã ẨN ${sourceName} khỏi Board (Vẫn hiện đầy đủ ở Discover)!`,
                        isBoardEnabled ? 'fa-tv' : 'fa-compass'
                    );
                    fetchAddons();
                } else {
                    showToast('Lỗi khi cập nhật cấu hình Board', 'fa-triangle-exclamation');
                }
            } catch (err) {
                showToast('Lỗi: ' + err.message, 'fa-triangle-exclamation');
            }
        }

        function renderAddonCards() {
            const env = document.getElementById('envUrlSelector')?.value || 'public';
            const fullGrid = document.getElementById('fullAddonsGrid');
            const overviewGrid = document.getElementById('overviewAddonsGrid');

            let fullHtml = '';
            let overviewHtml = '';

            cachedAddonsData.forEach(addon => {
                const isEnabled = addon.enabled !== false;
                const isBoardEnabled = addon.board_enabled !== false;
                const isSubtitle = addon.id === 'subtitles' || addon.is_subtitle_engine;
                const manifestUrl = addon.manifests[env] || addon.manifests['public'] || addon.manifests['lan'];
                const stremioInstallUrl = manifestUrl.replace('http://', 'stremio://').replace('https://', 'stremio://');
                const stremioWebUrl = `https://web.stremio.com/#/addons?addon=${encodeURIComponent(manifestUrl)}`;

                const statusBadge = isEnabled
                    ? `<span class="badge-tag" style="background:rgba(16,185,129,0.15);color:var(--success);border-color:rgba(16,185,129,0.3);font-size:11px;"><i class="fa-solid fa-circle-check" style="margin-right:4px;"></i>Bật</span>`
                    : `<span class="badge-tag" style="background:rgba(239,68,68,0.15);color:var(--danger);border-color:rgba(239,68,68,0.3);font-size:11px;"><i class="fa-solid fa-circle-xmark" style="margin-right:4px;"></i>Đã Tắt</span>`;

                const cardDisabledClass = isEnabled ? '' : 'card-disabled';

                const boardSectionHtml = isSubtitle ? '' : `
                        <!-- Stremio Board vs Discover Setting -->
                        <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-color); border-radius:var(--radius-md); padding:10px 12px; display:flex; align-items:center; justify-content:space-between; gap:10px;">
                            <div style="display:flex; align-items:center; gap:8px;">
                                <i class="fa-solid ${isBoardEnabled ? 'fa-tv' : 'fa-compass'}" style="color:${isBoardEnabled ? 'var(--primary)' : 'var(--text-dim)'}; font-size:14px;"></i>
                                <div>
                                    <div style="font-size:12px; font-weight:700; color:#fff;">Màn hình chính Stremio (Board)</div>
                                    <div style="font-size:11px; color:${isBoardEnabled ? 'var(--cyan)' : 'var(--text-dim)'};">
                                        ${isBoardEnabled ? '✨ Hiện ngoài Trang chủ & Khám phá' : '🔍 Chỉ hiện trong Khám phá (Discover)'}
                                    </div>
                                </div>
                            </div>
                            <label class="switch" style="transform:scale(0.85);" title="${isBoardEnabled ? 'Nhấp để ẨN khỏi Trang chủ (Chỉ xem trong mục Khám phá)' : 'Nhấp để HIỆN thanh phim ra Màn hình chính Stremio'}">
                                <input type="checkbox" ${isBoardEnabled ? 'checked' : ''} ${!isEnabled ? 'disabled' : ''} onchange="toggleBoardDisplay('${addon.id}', this.checked, '${addon.name}')">
                                <span class="slider"></span>
                            </label>
                        </div>
                `;

                const cardHtml = `
                    <div class="addon-card ${cardDisabledClass}">
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
                            <div style="display:flex; align-items:center; gap:8px;">
                                ${statusBadge}
                                <label class="switch" title="${isEnabled ? 'Nhấp để TẮT nguồn này' : 'Nhấp để BẬT nguồn này'}">
                                    <input type="checkbox" ${isEnabled ? 'checked' : ''} onchange="toggleMovieSource('${addon.id}', this.checked, '${addon.name}')">
                                    <span class="slider"></span>
                                </label>
                            </div>
                        </div>
                        <p class="addon-desc">${addon.description}</p>

                        ${boardSectionHtml}

                        ${!isEnabled ? '<div style="font-size:11.5px; color:#f87171; background:rgba(239,68,68,0.1); border:1px dashed rgba(239,68,68,0.3); border-radius:6px; padding:6px 10px; display:flex; align-items:center; gap:6px;"><i class="fa-solid fa-triangle-exclamation"></i> Nguồn/Dịch vụ này đang tắt</div>' : ''}

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
                            <a href="${stremioInstallUrl}" class="btn btn-primary btn-sm" style="justify-content:center; ${!isEnabled ? 'opacity:0.5; pointer-events:none;' : ''}">
                                <i class="fa-solid fa-download"></i> Cài Stremio
                            </a>
                            <a href="${stremioWebUrl}" target="_blank" class="btn btn-secondary btn-sm" style="justify-content:center; ${!isEnabled ? 'opacity:0.5; pointer-events:none;' : ''}">
                                <i class="fa-solid fa-globe"></i> Mở Web
                            </a>
                        </div>
                        ${(addon.player_url || addon.playlist_url) ? `
                        <div class="addon-actions" style="margin-top: 6px; display:flex; gap:8px;">
                            ${addon.playlist_url ? `
                            <button class="btn btn-secondary btn-sm" style="justify-content:center; flex:1; font-size:11px;" onclick="copyToClipboard('${addon.playlist_url}', '${addon.name} M3U Playlist')">
                                <i class="fa-solid fa-file-lines"></i> Copy M3U
                            </button>
                            ` : ''}
                            ${addon.player_url ? `
                            <a href="${addon.player_url}" target="_blank" class="btn btn-secondary btn-sm" style="justify-content:center; flex:1; font-size:11px;">
                                <i class="fa-solid fa-tv"></i> Web TV Player
                            </a>
                            ` : ''}
                        </div>
                        ` : ''}
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
            if (!url) return;
            if (chipEl) {
                document.querySelectorAll('.ep-chip').forEach(c => c.classList.remove('active'));
                chipEl.classList.add('active');
            }

            const video = document.getElementById('html5VideoPlayer');
            const iframe = document.getElementById('iframeVideoPlayer');

            if (hlsInstance) {
                hlsInstance.destroy();
                hlsInstance = null;
            }

            const isEmbedPlayer = url.includes('player_proxy') || url.includes('/player/') || (url.includes('embed') && !url.includes('.m3u8') && !url.includes('.mp4'));

            if (isEmbedPlayer) {
                video.pause();
                video.style.display = 'none';
                video.src = '';
                iframe.style.display = 'block';
                iframe.src = url;
            } else {
                iframe.style.display = 'none';
                iframe.src = '';
                video.style.display = 'block';

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
        }

        function closePlayerModal() {
            const video = document.getElementById('html5VideoPlayer');
            const iframe = document.getElementById('iframeVideoPlayer');
            video.pause();
            video.src = '';
            if (iframe) iframe.src = '';
            if (hlsInstance) {
                hlsInstance.destroy();
                hlsInstance = null;
            }
            document.getElementById('playerModal').classList.remove('active');
        }

        let rawLogsData = [];
        let currentLogLevelFilter = 'ALL';
        let isLogPaused = false;
        let logPollInterval = null;

        function getModuleBadge(name) {
            if (!name) return '';
            const n = name.toLowerCase();
            let cls = 'mod-default';
            let icon = 'fa-cube';
            if (n.includes('nguonc')) { cls = 'mod-nguonc'; icon = 'fa-film'; }
            else if (n.includes('film4k')) { cls = 'mod-film4k'; icon = 'fa-tv'; }
            else if (n.includes('iptv')) { cls = 'mod-iptv'; icon = 'fa-satellite-dish'; }
            else if (n.includes('vsmov')) { cls = 'mod-vsmov'; icon = 'fa-video'; }
            else if (n.includes('hhpanda')) { cls = 'mod-hhpanda'; icon = 'fa-dragon'; }
            else if (n.includes('moviesdrive')) { cls = 'mod-moviesdrive'; icon = 'fa-clapperboard'; }
            else if (n.includes('hdhub4u')) { cls = 'mod-hdhub4u'; icon = 'fa-bolt'; }
            else if (n.includes('topxx')) { cls = 'mod-topxx'; icon = 'fa-heart'; }
            else if (n.includes('ernax')) { cls = 'mod-ernax'; icon = 'fa-play-circle'; }
            else if (n.includes('vidking')) { cls = 'mod-vidking'; icon = 'fa-crown'; }
            else if (n.includes('tg') || n.includes('telegram')) { cls = 'mod-telegram'; icon = 'fa-brands fa-telegram'; }
            else if (n.includes('debrid') || n.includes('torbox') || n.includes('torrent') || n.includes('qbit')) { cls = 'mod-debrid'; icon = 'fa-cloud-arrow-down'; }
            else if (n.includes('sub') || n.includes('vtt') || n.includes('trans') || n.includes('tts') || n.includes('gemini')) { cls = 'mod-subtitles'; icon = 'fa-closed-captioning'; }
            else if (n.includes('uvicorn') || n.includes('fastapi') || n.includes('access')) { cls = 'mod-uvicorn'; icon = 'fa-server'; }
            else if (n.includes('addon') || n.includes('dashboard')) { cls = 'mod-addon'; icon = 'fa-layer-group'; }

            return `<span class="log-badge-module ${cls}"><i class="fa-solid ${icon}"></i> ${name}</span>`;
        }

        function getLevelIcon(level) {
            switch(level) {
                case 'INFO': return '<i class="fa-solid fa-circle-info"></i>';
                case 'WARNING': return '<i class="fa-solid fa-triangle-exclamation"></i>';
                case 'ERROR': return '<i class="fa-solid fa-circle-xmark"></i>';
                case 'CRITICAL': return '<i class="fa-solid fa-skull-crossbones"></i>';
                case 'DEBUG': return '<i class="fa-solid fa-bug"></i>';
                default: return '';
            }
        }

        function colorizeLogMessage(msg, searchKeyword = '') {
            if (!msg) return '';
            let text = String(msg)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;");

            // 1. Highlight HTTP Status Codes
            text = text.replace(/\b(200 OK|206 Partial Content|200|204|206|302 Found|304 Not Modified|301|302|304)\b/g, '<span class="code-success font-bold">$1</span>');
            text = text.replace(/\b(400 Bad Request|401 Unauthorized|403 Forbidden|404 Not Found|422 Unprocessable Entity|400|401|403|404|422)\b/g, '<span class="code-warning font-bold">$1</span>');
            text = text.replace(/\b(500 Internal Server Error|502 Bad Gateway|503 Service Unavailable|504 Gateway Timeout|500|502|503|504)\b/g, '<span class="code-danger font-bold">$1</span>');

            // 2. Highlight HTTP Methods
            text = text.replace(/\bGET\b/g, '<span class="code-method-get">GET</span>');
            text = text.replace(/\bPOST\b/g, '<span class="code-method-post">POST</span>');
            text = text.replace(/\b(OPTIONS|HEAD)\b/g, '<span class="code-method-opt">$1</span>');
            text = text.replace(/\b(DELETE|PUT|PATCH)\b/g, '<span class="code-method-del">$1</span>');

            // 3. Highlight IP Addresses & Ports
            text = text.replace(/\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d+)?)\b/g, '<span class="code-ip">$1</span>');

            // 4. Highlight Routes & URLs
            text = text.replace(/(https?:\/\/[^\s"',<]+)/g, '<span class="code-url">$1</span>');
            text = text.replace(/(\/(?:nguonc|vsmov|hhpanda|moviesdrive|hdhub4u|topxx|stream|manifest\.json|catalog|meta|configure|dashboard|admin|api)[^\s"',<]*)/g, '<span class="code-route">$1</span>');

            // 5. Highlight File Formats & Extensions
            text = text.replace(/(\.(?:m3u8|mp4|mkv|ts|vtt|srt|json|zip|torrent|avi|webm|mp3|aac))\b/gi, '<span class="code-file font-bold">$1</span>');

            // 6. Highlight Metrics & Units
            text = text.replace(/\b(\d+(?:\.\d+)?\s*(?:ms|s|MB|GB|KB|kbps|Mbps|fps| cues| items| entries| parts))\b/gi, '<span class="code-metric">$1</span>');

            // 7. Highlight Key Action & Status Words
            text = text.replace(/\b(Connected|Online|Restored|Success|Successfully|Ready|Started|Cached|Cache HIT|HIT|Resolved|Finished|Complete|Completed)\b/gi, '<span class="code-success font-bold">$1</span>');
            text = text.replace(/\b(Warning|Missing|Retry|Retrying|Timeout|deprecated|Slow|Bypass|fallback|skipping)\b/gi, '<span class="code-warning font-bold">$1</span>');
            text = text.replace(/\b(Disconnected|Offline|Stopped|Shutting down|Shutdown|Failed|Error|Exception|Crash|Refused|Cannot)\b/gi, '<span class="code-danger font-bold">$1</span>');

            // 8. Highlight Search Keyword if present
            if (searchKeyword && searchKeyword.length >= 2) {
                try {
                    const regex = new RegExp(`(${searchKeyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
                    text = text.replace(regex, '<mark class="log-highlight">$1</mark>');
                } catch(e) {}
            }

            return text;
        }

        function setLogLevelFilter(level, btnEl) {
            currentLogLevelFilter = level;
            document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
            if (btnEl) btnEl.classList.add('active');
            filterAndRenderLogs();
        }

        function toggleLogPause() {
            isLogPaused = !isLogPaused;
            const btn = document.getElementById('btnLogPause');
            if (isLogPaused) {
                btn.innerHTML = '<i class="fa-solid fa-play"></i> Tiếp Tục';
                btn.classList.replace('btn-secondary', 'btn-primary');
                showToast('Đã tạm dừng cập nhật log', 'fa-pause');
            } else {
                btn.innerHTML = '<i class="fa-solid fa-pause"></i> Tạm Dừng';
                btn.classList.replace('btn-primary', 'btn-secondary');
                showToast('Đang tiếp tục cập nhật log', 'fa-play');
                fetchLogs();
            }
        }

        function copyLogs() {
            if (!rawLogsData || rawLogsData.length === 0) {
                showToast('Không có dữ liệu log để sao chép', 'fa-triangle-exclamation');
                return;
            }
            const textToCopy = rawLogsData.map(log => `[${log.time}] [${log.level}] [${log.name || 'System'}] ${log.message}`).join('\n');
            navigator.clipboard.writeText(textToCopy).then(() => {
                showToast(`Đã sao chép ${rawLogsData.length} dòng log vào Clipboard!`, 'fa-check');
            }).catch(err => {
                showToast('Lỗi khi sao chép log', 'fa-triangle-exclamation');
            });
        }

        function clearConsoleDisplay() {
            rawLogsData = [];
            filterAndRenderLogs();
            showToast('Đã xóa trắng màn hình console!', 'fa-eraser');
        }

        function filterAndRenderLogs() {
            const consoleEl = document.getElementById('logConsole');
            const searchKeyword = (document.getElementById('logSearchInput')?.value || '').toLowerCase().trim();
            const autoScroll = document.getElementById('chkAutoScroll')?.checked ?? true;

            let countAll = 0, countInfo = 0, countWarn = 0, countErr = 0, countDebug = 0;

            rawLogsData.forEach(log => {
                countAll++;
                if (log.level === 'INFO') countInfo++;
                else if (log.level === 'WARNING') countWarn++;
                else if (log.level === 'ERROR' || log.level === 'CRITICAL') countErr++;
                else if (log.level === 'DEBUG') countDebug++;
            });

            if (document.getElementById('countAll')) document.getElementById('countAll').textContent = countAll;
            if (document.getElementById('countInfo')) document.getElementById('countInfo').textContent = countInfo;
            if (document.getElementById('countWarn')) document.getElementById('countWarn').textContent = countWarn;
            if (document.getElementById('countErr')) document.getElementById('countErr').textContent = countErr;
            if (document.getElementById('countDebug')) document.getElementById('countDebug').textContent = countDebug;

            let filtered = rawLogsData.filter(log => {
                if (currentLogLevelFilter !== 'ALL' && log.level !== currentLogLevelFilter) {
                    if (currentLogLevelFilter === 'ERROR' && log.level !== 'CRITICAL') return false;
                    if (currentLogLevelFilter !== 'ERROR') return false;
                }
                if (searchKeyword) {
                    const matchMsg = (log.message || '').toLowerCase().includes(searchKeyword);
                    const matchModule = (log.name || '').toLowerCase().includes(searchKeyword);
                    if (!matchMsg && !matchModule) return false;
                }
                return true;
            });

            if (filtered.length === 0) {
                consoleEl.innerHTML = '<div style="color:var(--text-dim); text-align:center; padding:30px;"><i class="fa-solid fa-magnifying-glass" style="margin-bottom:8px; display:block; font-size:18px;"></i>Không có dòng nhật ký nào khớp với bộ lọc.</div>';
                return;
            }

            consoleEl.innerHTML = filtered.map((log, idx) => {
                const colorizedMsg = colorizeLogMessage(log.message, searchKeyword);
                const moduleBadge = getModuleBadge(log.name);
                const levelIcon = getLevelIcon(log.level);
                const levelClass = log.level || 'INFO';
                return `
                    <div class="log-line log-row-${levelClass}">
                        <span class="log-idx">${idx + 1}</span>
                        <span class="log-time">${log.time}</span>
                        <span class="log-badge-level log-lvl-${levelClass}">${levelIcon} ${levelClass}</span>
                        ${moduleBadge}
                        <span class="log-msg-text">${colorizedMsg}</span>
                    </div>
                `;
            }).join('');

            if (autoScroll) {
                consoleEl.scrollTop = consoleEl.scrollHeight;
            }
        }

        async function fetchLogs() {
            if (isLogPaused) return;
            try {
                const res = await fetch('/api/system/logs');
                const data = await res.json();
                if (data.logs) {
                    rawLogsData = data.logs;
                    filterAndRenderLogs();
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
                fetchLogs();
            } catch (err) {
                showToast('Lỗi khi xóa cache', 'fa-triangle-exclamation');
            }
        }

        // Init
        window.addEventListener('DOMContentLoaded', () => {
            fetchSystemStatus();
            fetchAddons();
            fetchLogs();
            setInterval(fetchSystemStatus, 15000);
            setInterval(fetchLogs, 2500);
        });
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html)
