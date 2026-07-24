import logging
import asyncio

# Fix Pyrogram event loop crash on Python 3.12/3.14
try:
    asyncio.get_event_loop()
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
            except RuntimeError as e:
                if "Response content shorter than Content-Length" in str(e):
                    return
                raise e
        try:
            await super().__call__(scope, receive, safe_send)
        except RuntimeError as e:
            if "Response content shorter than Content-Length" in str(e):
                return
            raise e

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
        
        Config.validate()
        await tg_client_manager.start()
        yield
    finally:
        await tg_client_manager.stop()

from nguonc_router import nguonc_router
from vsmov_router import vsmov_router

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(nguonc_router, prefix="/nguonc", tags=["NguonC Cinema"])
app.include_router(vsmov_router, prefix="/vsmov", tags=["VSMov Cinema"])



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
    return {
        "id": "community.telegram.stremio.addon",
        "version": "1.0.0",
        "name": "Telegram Addon by SunilRoy-dev",
        "description": "Personal Telegram streaming proxy. For educational & personal testing only. Do not use for unauthorized hosting of copyrighted media.",
        "logo": "https://upload.wikimedia.org/wikipedia/commons/8/82/Telegram_logo.svg",
        "resources": ["meta", "stream", "subtitles"],
        "types": ["movie", "series", "anime", "other"],
        "catalogs": [
            {
                "type": "movie",
                "id": "telegram_movies",
                "name": "Telegram Movies",
                "extra": [{"name": "search", "isRequired": False}, {"name": "skip", "isRequired": False}]
            },
            {
                "type": "series",
                "id": "telegram_series",
                "name": "Telegram Series",
                "extra": [{"name": "search", "isRequired": False}, {"name": "skip", "isRequired": False}]
            }
        ],
        "behaviorHints": {
            "configurable": False,
            "configurationRequired": False
        }
    }

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def landing(request: Request):
    api_key = request.query_params.get("api_key", "")
    if api_key:
        manifest_url = f"{Config.ADDON_URL}/{urllib.parse.quote(api_key)}/manifest.json"
    else:
        manifest_url = f"{Config.ADDON_URL}/manifest.json"
        
    escaped_manifest_url = markupsafe.escape(manifest_url)
    escaped_stremio_url = markupsafe.escape(manifest_url.replace('http://', '').replace('https://', ''))
    
    web_stremio_url = f"https://web.stremio.com/#/addons?addon={urllib.parse.quote(manifest_url)}"
    escaped_web_stremio_url = markupsafe.escape(web_stremio_url)
    
    api_key_section = ""
    if Config.API_KEY:
        escaped_api_key = markupsafe.escape(api_key)
        api_key_section = f"""
                <div class="url-section" style="margin-bottom: 16px;">
                    <div class="section-title">Enter API Key</div>
                    <div class="input-group">
                        <input class="url-box" id="apiKeyInput" type="text" placeholder="Enter your API Key..." value="{escaped_api_key}" oninput="updateManifestUrl()">
                    </div>
                </div>
        """
        
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Telegram Addon by SunilRoy-dev</title>
            <meta name="description" content="Stream private Telegram files directly inside Stremio. Secure, lightweight, and ranges-supported proxy.">
            <link rel="preconnect" href="https://fonts.googleapis.com">
            <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
            <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
            <style>
                :root {{
                    --bg-dark: #09090b;
                    --bg-card: #18181b;
                    --border-muted: #27272a;
                    --text-primary: #f4f4f5;
                    --text-secondary: #a1a1aa;
                    --text-muted: #71717a;
                    --color-primary: #2563eb;
                    --color-primary-hover: #1d4ed8;
                    --color-accent: #60a5fa;
                    --font-title: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    --font-body: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                }}
                * {{
                    box-sizing: border-box;
                    margin: 0;
                    padding: 0;
                }}
                body {{
                    font-family: var(--font-body);
                    background-color: var(--bg-dark);
                    color: var(--text-primary);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    padding: 40px 20px;
                    margin: 0;
                    overflow-x: hidden;
                }}
                .app-card {{
                    background-color: var(--bg-card);
                    border: 1px solid var(--border-muted);
                    border-radius: 12px;
                    padding: 40px;
                    width: 100%;
                    max-width: 680px;
                    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
                    position: relative;
                }}
                .nav-header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 32px;
                }}
                .brand {{
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    font-family: var(--font-title);
                    font-weight: 700;
                    font-size: 1.1rem;
                    letter-spacing: -0.02em;
                    color: var(--text-primary);
                }}
                .brand-logo {{
                    width: 28px;
                    height: 28px;
                }}
                .star-badge {{
                    display: inline-flex;
                    align-items: center;
                    gap: 6px;
                    background: linear-gradient(135deg, #fbbf24 0%, #d97706 100%);
                    color: #09090b;
                    padding: 8px 14px;
                    border-radius: 6px;
                    font-size: 0.78rem;
                    font-weight: 700;
                    text-decoration: none;
                    box-shadow: 0 0 15px rgba(251, 191, 36, 0.3);
                    transition: all 0.3s ease;
                }}
                .star-badge:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 0 20px rgba(251, 191, 36, 0.6);
                    color: #000000;
                }}
                .hero {{
                    text-align: center;
                    margin-bottom: 32px;
                }}
                .hero h1 {{
                    font-family: var(--font-title);
                    font-size: 2rem;
                    font-weight: 700;
                    line-height: 1.25;
                    letter-spacing: -0.02em;
                    margin: 8px 0 16px 0;
                    color: #ffffff;
                }}
                .hero p {{
                    font-size: 0.95rem;
                    color: var(--text-secondary);
                    line-height: 1.5;
                    max-width: 520px;
                    margin: 0 auto;
                }}
                .url-section {{
                    background: #09090b;
                    border: 1px solid var(--border-muted);
                    border-radius: 8px;
                    padding: 20px;
                    margin-bottom: 24px;
                }}
                .section-title {{
                    font-family: var(--font-title);
                    font-size: 0.8rem;
                    font-weight: 700;
                    text-transform: uppercase;
                    letter-spacing: 0.05em;
                    color: var(--text-secondary);
                    margin-bottom: 12px;
                }}
                .input-group {{
                    display: flex;
                    gap: 10px;
                }}
                .url-box {{
                    flex: 1;
                    background-color: #18181b;
                    border: 1px solid #27272a;
                    color: var(--text-primary);
                    padding: 12px 16px;
                    border-radius: 6px;
                    font-size: 0.85rem;
                    font-family: monospace;
                    outline: none;
                    transition: border-color 0.2s;
                }}
                .url-box:focus {{
                    border-color: var(--color-primary);
                }}
                .btn-copy {{
                    background: #27272a;
                    border: 1px solid #3f3f46;
                    color: var(--text-primary);
                    padding: 0 16px;
                    border-radius: 6px;
                    font-size: 0.85rem;
                    font-weight: 500;
                    cursor: pointer;
                    display: inline-flex;
                    align-items: center;
                    gap: 6px;
                    transition: all 0.2s;
                }}
                .btn-copy:hover {{
                    background: #3f3f46;
                    border-color: #52525b;
                }}
                .button-group {{
                    display: grid;
                    grid-template-columns: 1fr;
                    gap: 12px;
                    margin-bottom: 32px;
                }}
                @media (min-width: 520px) {{
                    .button-group {{
                        grid-template-columns: 1fr 1fr;
                    }}
                }}
                .btn {{
                    padding: 12px 20px;
                    font-family: var(--font-body);
                    font-size: 0.9rem;
                    font-weight: 500;
                    text-decoration: none;
                    border-radius: 6px;
                    text-align: center;
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    gap: 8px;
                    transition: all 0.2s;
                }}
                .btn-primary {{
                    background-color: var(--color-primary);
                    color: #ffffff;
                }}
                .btn-primary:hover {{
                    background-color: var(--color-primary-hover);
                }}
                .btn-secondary {{
                    background: #27272a;
                    border: 1px solid #3f3f46;
                    color: var(--text-primary);
                }}
                .btn-secondary:hover {{
                    background: #3f3f46;
                    border-color: #52525b;
                }}
                .troubleshoot-details {{
                    background: #09090b;
                    border: 1px solid var(--border-muted);
                    border-radius: 8px;
                    padding: 16px;
                    margin-bottom: 24px;
                }}
                .troubleshoot-summary {{
                    font-family: var(--font-title);
                    font-size: 0.9rem;
                    font-weight: 600;
                    color: var(--text-primary);
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    user-select: none;
                    outline: none;
                }}
                .troubleshoot-content {{
                    margin-top: 14px;
                    font-size: 0.85rem;
                    color: var(--text-secondary);
                    line-height: 1.5;
                    border-top: 1px solid #27272a;
                    padding-top: 14px;
                }}
                .troubleshoot-content ol {{
                    margin-left: 20px;
                    margin-top: 8px;
                }}
                .troubleshoot-content li {{
                    margin-bottom: 6px;
                }}
                .features-grid {{
                    display: grid;
                    grid-template-columns: 1fr;
                    gap: 16px;
                    margin-bottom: 32px;
                }}
                @media (min-width: 600px) {{
                    .features-grid {{
                        grid-template-columns: 1fr 1fr;
                    }}
                }}
                .feature-card {{
                    background: #18181b;
                    border: 1px solid var(--border-muted);
                    border-radius: 8px;
                    padding: 20px;
                }}
                .feature-icon {{
                    width: 36px;
                    height: 36px;
                    background: #27272a;
                    border-radius: 6px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: var(--color-accent);
                    margin-bottom: 12px;
                }}
                .feature-title {{
                    font-family: var(--font-title);
                    font-size: 0.95rem;
                    font-weight: 600;
                    margin-bottom: 6px;
                    color: var(--text-primary);
                }}
                .feature-desc {{
                    font-size: 0.8rem;
                    color: var(--text-secondary);
                    line-height: 1.45;
                }}
                .license-card {{
                    background: #18181b;
                    border: 1px solid var(--border-muted);
                    border-radius: 8px;
                    padding: 20px;
                    margin-bottom: 32px;
                }}
                .license-title {{
                    font-family: var(--font-title);
                    font-size: 0.9rem;
                    font-weight: 600;
                    color: var(--text-primary);
                    margin-bottom: 6px;
                }}
                .license-text {{
                    font-size: 0.8rem;
                    color: var(--text-secondary);
                    line-height: 1.45;
                }}
                .footer {{
                    text-align: center;
                    font-size: 0.78rem;
                    color: var(--text-muted);
                    border-top: 1px solid var(--border-muted);
                    padding-top: 24px;
                    line-height: 1.6;
                }}
                .footer a {{
                    color: var(--text-secondary);
                    text-decoration: none;
                    font-weight: 500;
                    transition: color 0.2s;
                }}
                .footer a:hover {{
                    color: var(--text-primary);
                    text-decoration: underline;
                }}
                .footer em {{
                    display: block;
                    margin-top: 6px;
                    color: var(--text-muted);
                    font-style: normal;
                }}
            </style>
        </head>
        <body>
            <div class="app-card">
                <div class="nav-header">
                    <div class="brand">
                        <svg class="brand-logo" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z" fill="url(#logoGrad)"/>
                            <path fill-rule="evenodd" clip-rule="evenodd" d="M16.974 8.23272C17.1568 7.2796 16.2004 6.5492 15.3533 6.94008L6.46743 11.0398C5.72727 11.3813 5.76103 12.4431 6.51651 12.7336L8.85507 13.6331C9.52554 13.891 10.2831 13.7828 10.8553 13.3486L14.4754 10.6011C14.6195 10.4917 14.7766 10.7042 14.6534 10.8406L11.597 14.2238C11.107 14.7663 11.2335 15.6322 11.854 16.015L15.3854 18.1936C16.1471 18.6635 17.1264 18.0673 17.0792 17.1685L16.974 8.23272Z" fill="white"/>
                            <defs>
                                <linearGradient id="logoGrad" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
                                    <stop stop-color="#3b82f6"/>
                                    <stop offset="1" stop-color="#1d4ed8"/>
                                </linearGradient>
                            </defs>
                        </svg>
                        Stremio Telegram Addon
                    </div>
                    <div class="header-actions">
                        <a href="https://github.com/SunilRoy-dev/stremio-telegram-debrid" target="_blank" class="star-badge">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" stroke="none" style="margin-right: 4px;"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>
                            Star on GitHub
                        </a>
                    </div>
                </div>
                
                <div class="hero">
                    <h1>Stremio Telegram Addon</h1>
                    <p>A self-hosted Stremio addon proxy to stream videos, audios, and segmented archive parts directly from Telegram.</p>
                </div>
                
                {api_key_section}
                <div class="url-section">
                    <div class="section-title">Addon Manifest URL</div>
                    <div class="input-group">
                        <input class="url-box" id="manifestUrl" type="text" readonly value="{escaped_manifest_url}">
                        <button class="btn-copy" id="btnCopy" onclick="copyManifestUrl()">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="feather feather-copy"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                            <span id="btnCopyText">Copy</span>
                        </button>
                    </div>
                </div>
                
                <div class="button-group">
                    <a class="btn btn-primary" id="installApp" href="stremio://{escaped_stremio_url}">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                        Install on Stremio App
                    </a>
                    <a class="btn btn-secondary" id="installWeb" href="{escaped_web_stremio_url}" target="_blank">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                        Install on Stremio Web
                    </a>
                </div>
                
                <details class="troubleshoot-details">
                    <summary class="troubleshoot-summary">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 8px; color: #fbbf24;"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                        Local Deployment Troubleshooting
                    </summary>
                    <div class="troubleshoot-content">
                        This error <strong>only occurs in local HTTP deployments</strong>. If you deploy this project to a secure public HTTPS server (such as Hugging Face Spaces, Render, or Koyeb), this installation button will work <strong>flawlessly</strong>.
                        <br><br>
                        For local deployments, Stremio's desktop protocol handler (<strong>stremio://</strong>) strips local ports and forces HTTPS, resulting in connection failure.
                        <br><br>
                        <strong>How to install locally:</strong>
                        <ol>
                            <li>Click the <strong>Copy</strong> button on the manifest URL field above.</li>
                            <li>Open the <strong>Stremio Desktop App</strong>.</li>
                            <li>Navigate to <strong>Add-ons</strong> (puzzle icon in the sidebar).</li>
                            <li>Paste the copied URL directly into the <strong>Add-on Repository URL</strong> input box at the bottom and click <strong>Install</strong>.</li>
                            <li>Alternatively, use the <strong>Install on Stremio Web</strong> button above.</li>
                        </ol>
                    </div>
                </details>
                
                <div class="features-grid">
                    <div class="feature-card">
                        <div class="feature-icon">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>
                        </div>
                        <div class="feature-title">Segmented File Stitching</div>
                        <div class="feature-desc">Groups and stitches split file parts (.001, .part1, etc.) into a virtual continuous stream on the fly.</div>
                    </div>
                    <div class="feature-card">
                        <div class="feature-icon">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
                        </div>
                        <div class="feature-title">Range-Seek Support</div>
                        <div class="feature-desc">Full byte-range support allows you to skip forward or seek backward instantly inside your media player.</div>
                    </div>
                    <div class="feature-card">
                        <div class="feature-icon">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                        </div>
                        <div class="feature-title">Subtitle Mapping</div>
                        <div class="feature-desc">Scans the channel dynamically for matching subtitle files (.srt, .vtt, .ass) and injects them.</div>
                    </div>
                    <div class="feature-card">
                        <div class="feature-icon">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
                        </div>
                        <div class="feature-title">Access Control</div>
                        <div class="feature-desc">Protects endpoints with a secure API key check to prevent unauthorized use of your proxy.</div>
                    </div>
                </div>
                
                <div class="license-card">
                    <div class="license-title">License: MIT Non-Commercial License (MIT-NC)</div>
                    <div class="license-text">
                        This software is published under a custom <strong>MIT Non-Commercial License (MIT-NC)</strong>. Sublicensing, commercial distribution, renting, or monetization of this code or its derivatives is strictly prohibited. Attribution must be preserved in all copies.
                    </div>
                </div>
                
                <div class="footer">
                    Developed by <a href="https://github.com/SunilRoy-dev" target="_blank">SunilRoy-dev</a> | Licensed under MIT-NC
                    <em>For educational and personal testing only. Do not use for unauthorized hosting or distribution of copyrighted media.</em>
                </div>
            </div>
            
            <script>
                const baseManifestUrl = "{Config.ADDON_URL}/manifest.json";
                const baseStremioUrl = baseManifestUrl.replace('http://', '').replace('https://', '');
                
                function updateManifestUrl() {{
                    const apiKeyInput = document.getElementById("apiKeyInput");
                    const manifestUrlEl = document.getElementById("manifestUrl");
                    const installAppEl = document.getElementById("installApp");
                    const installWebEl = document.getElementById("installWeb");
                    
                    let apiKey = "";
                    if (apiKeyInput) {{
                        apiKey = apiKeyInput.value.trim();
                    }} else {{
                        apiKey = new URLSearchParams(window.location.search).get("api_key") || "";
                    }}
                    
                    let manifestUrl = baseManifestUrl;
                    let stremioUrl = baseStremioUrl;
                    
                    if (apiKey) {{
                        const encodedKey = encodeURIComponent(apiKey);
                        manifestUrl = "{Config.ADDON_URL}/" + encodedKey + "/manifest.json";
                        stremioUrl = baseStremioUrl.replace("manifest.json", encodedKey + "/manifest.json");
                    }}
                    
                    if (manifestUrlEl) {{
                        manifestUrlEl.value = manifestUrl;
                    }}
                    if (installAppEl) {{
                        installAppEl.href = "stremio://" + stremioUrl;
                    }}
                    if (installWebEl) {{
                        installWebEl.href = "https://web.stremio.com/#/addons?addon=" + encodeURIComponent(manifestUrl);
                    }}
                }}

                function copyManifestUrl() {{
                    var copyText = document.getElementById("manifestUrl");
                    copyText.select();
                    copyText.setSelectionRange(0, 99999);
                    navigator.clipboard.writeText(copyText.value);
                    
                    var btnText = document.getElementById("btnCopyText");
                    var originalText = btnText.innerHTML;
                    btnText.innerHTML = "Copied!";
                    
                    var copyBtn = document.getElementById("btnCopy");
                    
                    copyBtn.style.background = "#22c55e";
                    copyBtn.style.borderColor = "#22c55e";
                    copyBtn.style.color = "#ffffff";
                    
                    setTimeout(function() {{
                        btnText.innerHTML = originalText;
                        copyBtn.style.background = "";
                        copyBtn.style.borderColor = "";
                        copyBtn.style.color = "";
                    }}, 2000);
                }}

                window.onload = function() {{
                    updateManifestUrl();
                }};
            </script>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.api_route("/manifest.json", methods=["GET", "HEAD"])
@app.api_route("/{api_key}/manifest.json", methods=["GET", "HEAD"])
async def manifest_endpoint(api_key: str = ""):
    if Config.API_KEY and api_key != Config.API_KEY:
        return JSONResponse({"detail": "Unauthorized: Invalid API Key"}, status_code=403)
    return get_manifest(api_key)

@app.get("/catalog/{type}/{catalog_id}.json", dependencies=[Depends(verify_api_key)])
@app.get("/catalog/{type}/{catalog_id}/{extra}.json", dependencies=[Depends(verify_api_key)])
@app.get("/{api_key}/catalog/{type}/{catalog_id}.json", dependencies=[Depends(verify_api_key)])
@app.get("/{api_key}/catalog/{type}/{catalog_id}/{extra}.json", dependencies=[Depends(verify_api_key)])
async def catalog_handler(
    type: str, 
    catalog_id: str, 
    extra: str = None,
    api_key: str = ""
):
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
            "background": f"{Config.ADDON_URL}/stremio_telegram_banner.png" if getattr(Config, "ADDON_URL", None) else None,
            "logo": f"{Config.ADDON_URL}/stremio_telegram_logo.png" if getattr(Config, "ADDON_URL", None) else None,
        }
        
        if type == "series":
            meta["videos"] = [
                {
                    "id": meta_id,
                    "title": file_name,
                    "season": 1,
                    "episode": 1
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
            
            query_str = urllib.parse.urlencode(params)
            sub_url = f"{Config.ADDON_URL}/stream/subtitle/autoviet/{cache_key}"
            if query_str:
                sub_url += f"?{query_str}"
            
            subtitles.append({
                "id": f"autovietsub_{cache_key}",
                "url": sub_url,
                "lang": "vie"
            })
            
            # Preload in background
            asyncio.create_task(subtitle_generator.get_or_start_translation(
                cache_key=cache_key,
                source_url=source_url,
                video_url=video_url,
                filename=video_filename
            ))
            
    return subtitles

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


_thumb_file_id_cache = {}
_thumb_download_semaphore = asyncio.Semaphore(2)
_thumb_resolve_semaphore = asyncio.Semaphore(1)
_active_thumb_downloads = set()
_failed_thumb_downloads = {}  # cache_key -> (timestamp, count)

async def _download_thumb_task(chat_id: str, msg_id: int, thumb_file_id: str, thumb_path: str):
    import time
    import shutil
    cache_key = f"{chat_id}_{msg_id}"
    if cache_key in _active_thumb_downloads:
        return
        
    default_logo = "stremio_telegram_logo.png"
    now = time.time()
    if cache_key in _failed_thumb_downloads:
        last_time, count = _failed_thumb_downloads[cache_key]
        # Cooldown of 5 minutes between download attempts
        if now - last_time < 300:
            return
        # If failed 3 or more times, copy default logo to prevent future attempts
        if count >= 3:
            if os.path.exists(default_logo) and not os.path.exists(thumb_path):
                try:
                    os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
                    shutil.copy(default_logo, thumb_path)
                except Exception as ce:
                    logger.error(f"Failed to copy default logo to {thumb_path}: {ce}")
            return

    _active_thumb_downloads.add(cache_key)
    try:
        # Wait 1.0s before starting to queue up multiple parallel catalog loads gently
        await asyncio.sleep(1.0)
        async with _thumb_download_semaphore:
            if not os.path.exists(thumb_path):
                logger.info(f"Background downloading Telegram thumbnail for message {msg_id} in {chat_id}...")
                await tg_client_manager.client.download_media(
                    thumb_file_id,
                    file_name=thumb_path
                )
                # Pause between downloads to keep Telegram DC connection happy
                await asyncio.sleep(1.5)
        # Clear failure tracking on success
        if os.path.exists(thumb_path):
            _failed_thumb_downloads.pop(cache_key, None)
    except Exception as e:
        logger.error(f"Failed to background download Telegram thumbnail for {cache_key}: {e}")
        now = time.time()
        _, count = _failed_thumb_downloads.get(cache_key, (0, 0))
        _failed_thumb_downloads[cache_key] = (now, count + 1)
    finally:
        _active_thumb_downloads.discard(cache_key)


def get_message_thumbnail_url(msg, logo_url: str) -> str:
    if not msg:
        return logo_url
    media = msg.video or msg.document
    logger.info(f"get_message_thumbnail_url: msg={msg.id}, media={type(media).__name__ if media else None}, thumbs={len(media.thumbs) if media and getattr(media, 'thumbs', None) else 0}")
    if media:
        thumb = getattr(media, "thumb", None)
        if thumb and getattr(thumb, "file_id", None):
            chat_id = msg.chat.id
            msg_id = msg.id
            _thumb_file_id_cache[f"{chat_id}_{msg_id}"] = thumb.file_id
            query = f"?api_key={Config.API_KEY}" if Config.API_KEY else ""
            return f"{Config.ADDON_URL}/thumbnail/{chat_id}/{msg_id}.jpg{query}"
            
        thumbs = getattr(media, "thumbs", None)
        if thumbs and isinstance(thumbs, list) and thumbs:
            chat_id = msg.chat.id
            msg_id = msg.id
            _thumb_file_id_cache[f"{chat_id}_{msg_id}"] = thumbs[0].file_id
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
            
    import os
    temp_dir = os.path.join("temp_cache", "thumbs")
    os.makedirs(temp_dir, exist_ok=True)
    
    thumb_path = os.path.join(temp_dir, f"{chat_id}_{msg_id}.jpg")
    default_logo = "stremio_telegram_logo.png"
    
    # 1. Serve immediately if cached on disk
    if os.path.exists(thumb_path):
        return FileResponse(thumb_path)
        
    cache_key = f"{chat_id}_{msg_id}"
    thumb_file_id = _thumb_file_id_cache.get(cache_key)
    
    # 2. If cached in memory, trigger background download and return fallback immediately
    if thumb_file_id:
        if cache_key not in _active_thumb_downloads:
            asyncio.create_task(_download_thumb_task(chat_id, msg_id, thumb_file_id, thumb_path))
            
        if os.path.exists(default_logo):
            return FileResponse(default_logo)
        raise HTTPException(status_code=404, detail="Fallback logo not found")
        
    # 3. If not cached, resolve the message in the background to prevent blocking
    async def resolve_and_download():
        import time
        import shutil
        if cache_key in _active_thumb_downloads:
            return
            
        now = time.time()
        if cache_key in _failed_thumb_downloads:
            last_time, count = _failed_thumb_downloads[cache_key]
            # Cooldown of 5 minutes between resolution attempts
            if now - last_time < 300:
                return
            # If failed 3 or more times, copy default logo to prevent future attempts
            if count >= 3:
                if os.path.exists(default_logo) and not os.path.exists(thumb_path):
                    try:
                        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
                        shutil.copy(default_logo, thumb_path)
                    except Exception as ce:
                        logger.error(f"Failed to copy default logo to {thumb_path}: {ce}")
                return

        _active_thumb_downloads.add(cache_key)
        try:
            async with _thumb_resolve_semaphore:
                # Sleep a little to pace out requests to Telegram API
                await asyncio.sleep(0.5)
                
                try:
                    chat_id_val = int(chat_id)
                except ValueError:
                    chat_id_val = chat_id
                    
                msg = await tg_client_manager.get_message(msg_id, chat_id=chat_id_val)
                
                has_thumb = False
                if msg:
                    media = msg.video or msg.document
                    if media:
                        thumb = getattr(media, "thumb", None)
                        fid = None
                        if thumb and getattr(thumb, "file_id", None):
                            fid = thumb.file_id
                        else:
                            thumbs = getattr(media, "thumbs", None)
                            if thumbs and isinstance(thumbs, list) and thumbs:
                                fid = thumbs[0].file_id
                                
                        if fid:
                            has_thumb = True
                            _thumb_file_id_cache[cache_key] = fid
                            # Release the lock for this key so download task can lock it
                            _active_thumb_downloads.discard(cache_key)
                            await _download_thumb_task(chat_id, msg_id, fid, thumb_path)
                            
                if not has_thumb:
                    logger.info(f"No thumbnail found for message {msg_id} in {chat_id}. Using fallback.")
                    if os.path.exists(default_logo) and not os.path.exists(thumb_path):
                        try:
                            os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
                            shutil.copy(default_logo, thumb_path)
                        except Exception as ce:
                            logger.error(f"Failed to copy default logo to {thumb_path}: {ce}")
                        # Clear failure tracking since we have a permanent fallback now
                        _failed_thumb_downloads.pop(cache_key, None)
                        
        except Exception as e:
            logger.warning(f"Background thumbnail resolution failed for {cache_key}: {e}")
            now = time.time()
            _, count = _failed_thumb_downloads.get(cache_key, (0, 0))
            _failed_thumb_downloads[cache_key] = (now, count + 1)
        finally:
            _active_thumb_downloads.discard(cache_key)
            
    if cache_key not in _active_thumb_downloads:
        asyncio.create_task(resolve_and_download())
        
    if os.path.exists(default_logo):
        return FileResponse(default_logo)
        
    raise HTTPException(status_code=404, detail="Thumbnail not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("addon:app", host="0.0.0.0", port=Config.PORT, reload=True)
