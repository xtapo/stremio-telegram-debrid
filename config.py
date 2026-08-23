import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _env_float(name, default):
    """Read a float from the environment, falling back on any bad value."""
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return float(default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _env_int(name, default):
    """Read an int from the environment, falling back on any bad value."""
    return int(_env_float(name, float(default)))


class Config:
    PORT = int(os.getenv("PORT", 7860))
    ADDON_URL = os.getenv("ADDON_URL", f"http://localhost:{PORT}").rstrip("/")
    API_KEY = os.getenv("API_KEY", "")
    DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME", os.getenv("ADMIN_USERNAME", "admin"))
    DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", os.getenv("ADMIN_PASSWORD", os.getenv("API_KEY", "")))
    CACHE_TTL = int(os.getenv("CACHE_TTL", 1800))
    TIMEZONE = os.getenv("TIMEZONE", "UTC")
    STREAM_CACHE_SIZE_MB = int(os.getenv("STREAM_CACHE_SIZE_MB", 512))
    PREFETCH_CHUNKS = int(os.getenv("PREFETCH_CHUNKS", 1))
    REAL_DEBRID_API_KEY = os.getenv("REAL_DEBRID_API_KEY", "")
    TORBOX_API_KEY = os.getenv("TORBOX_API_KEY", "")
    JACKETT_URL = os.getenv("JACKETT_URL", "")
    JACKETT_API_KEY = os.getenv("JACKETT_API_KEY", "")
    PROWLARR_URL = os.getenv("PROWLARR_URL", "")
    PROWLARR_API_KEY = os.getenv("PROWLARR_API_KEY", "")
    AUTO_UPLOAD_TO_TELEGRAM = os.getenv("AUTO_UPLOAD_TO_TELEGRAM", "True").lower() == "true"
    MAX_TORRENT_RESULTS = int(os.getenv("MAX_TORRENT_RESULTS", 10))
    QBITTORRENT_URL = os.getenv("QBITTORRENT_URL", "")
    QBITTORRENT_USER = os.getenv("QBITTORRENT_USER", "admin")
    QBITTORRENT_PASS = os.getenv("QBITTORRENT_PASS", "adminadmin")
    QBITTORRENT_PLAY_DIR = os.getenv("QBITTORRENT_PLAY_DIR", "")
    ENABLE_SUBTITLES = os.getenv("ENABLE_SUBTITLES", "True").lower() == "true"
    AUTO_VIET_SUB = os.getenv("AUTO_VIET_SUB", "True").lower() == "true"
    
    # Gemini AI translation settings
    ENABLE_GEMINI = os.getenv("ENABLE_GEMINI", os.getenv("GEMINI_ENABLED", "True")).lower() == "true"
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    AUTO_THUYET_MINH = os.getenv("AUTO_THUYET_MINH", "True").lower() == "true"
    
    # Custom AI translation settings
    ENABLE_CUSTOM_AI = os.getenv("ENABLE_CUSTOM_AI", os.getenv("CUSTOM_AI_ENABLED", "True")).lower() == "true"
    CUSTOM_AI_API_KEY = os.getenv("CUSTOM_AI_API_KEY", "")
    CUSTOM_AI_API_URL = os.getenv("CUSTOM_AI_API_URL", "")
    CUSTOM_AI_MODEL = os.getenv("CUSTOM_AI_MODEL", "cc/claude-opus-4-6")
    CUSTOM_AI_STREAM = os.getenv("CUSTOM_AI_STREAM", "True").lower() == "true"
    # Movie Sources Enable/Disable Toggles
    ENABLE_SOURCE_TELEGRAM = os.getenv("ENABLE_SOURCE_TELEGRAM", "True").lower() == "true"
    ENABLE_SOURCE_NGUONC = os.getenv("ENABLE_SOURCE_NGUONC", "True").lower() == "true"
    ENABLE_SOURCE_VSMOV = os.getenv("ENABLE_SOURCE_VSMOV", "True").lower() == "true"
    ENABLE_SOURCE_HHPANDA = os.getenv("ENABLE_SOURCE_HHPANDA", "True").lower() == "true"
    ENABLE_SOURCE_MOVIESDRIVE = os.getenv("ENABLE_SOURCE_MOVIESDRIVE", "True").lower() == "true"
    ENABLE_SOURCE_HDHUB4U = os.getenv("ENABLE_SOURCE_HDHUB4U", "True").lower() == "true"
    ENABLE_SOURCE_UHDMOVIES = os.getenv("ENABLE_SOURCE_UHDMOVIES", "True").lower() == "true"
    ENABLE_SOURCE_TOPXX = os.getenv("ENABLE_SOURCE_TOPXX", "True").lower() == "true"
    ENABLE_SOURCE_HDTODAY = os.getenv("ENABLE_SOURCE_HDTODAY", "True").lower() == "true"
    ENABLE_SOURCE_VIDKING = os.getenv("ENABLE_SOURCE_VIDKING", "True").lower() == "true"
    ENABLE_SOURCE_ERNAX = os.getenv("ENABLE_SOURCE_ERNAX", "True").lower() == "true"
    ENABLE_SOURCE_FILM4K_TV = os.getenv("ENABLE_SOURCE_FILM4K_TV", "True").lower() == "true"
    ENABLE_SOURCE_4KHDHUB = os.getenv("ENABLE_SOURCE_4KHDHUB", "True").lower() == "true"
    ENABLE_SOURCE_IPTV = os.getenv("ENABLE_SOURCE_IPTV", os.getenv("ENABLE_SOURCE_IPTV_ORG", "True")).lower() == "true"
    ENABLE_SOURCE_MOVIES2WATCH = os.getenv("ENABLE_SOURCE_MOVIES2WATCH", "True").lower() == "true"
    UHDMOVIES_BASE_URL = os.getenv("UHDMOVIES_BASE_URL", "https://uhdmovies.autos").rstrip("/")
    FOURKHDHUB_BASE_URL = os.getenv("FOURKHDHUB_BASE_URL", "https://4khdhub.one").rstrip("/")
    HDTODAY_BASE_URL = os.getenv("HDTODAY_BASE_URL", "https://hdtoday.sc").rstrip("/")
    MOVIES2WATCH_BASE_URL = os.getenv("MOVIES2WATCH_BASE_URL", "https://movies2watch.vc").rstrip("/")
    FILM4K_BASE_URL = os.getenv("FILM4K_BASE_URL", "https://film4k.net").rstrip("/")
    FILM4K_COOKIE = os.getenv("FILM4K_COOKIE", "session=eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImphbWlkMjA0QGdtYWlsLmNvbSIsIm5hbWUiOiJUaGkgVHJhbiIsImltYWdlIjoiaHR0cHM6Ly9saDMuZ29vZ2xldXNlcmNvbnRlbnQuY29tL2EvQUNnOG9jSV9HWURzQ3JHaFV4WUN1NVRkNWxka3laRHUxcm5TSUJQVGU0dkJKZUFaalhWYW95aUc9czk2LWMiLCJzdWIiOiI2YTg4NDYyOGQ5MmQwNmI3OTRjNjQ2NzUiLCJpYXQiOjE3ODczMTU3NTIsImV4cCI6MTc4OTkwNzc1Mn0.nNwoSi3H9HwNkYCYVTj4PhS0IVKoAdus4racY3pOMBo")

    # Stremio Board (Home Screen) vs Discover Only Toggles
    ENABLE_BOARD_TELEGRAM = os.getenv("ENABLE_BOARD_TELEGRAM", "True").lower() == "true"
    ENABLE_BOARD_NGUONC = os.getenv("ENABLE_BOARD_NGUONC", "True").lower() == "true"
    ENABLE_BOARD_VSMOV = os.getenv("ENABLE_BOARD_VSMOV", "True").lower() == "true"
    ENABLE_BOARD_HHPANDA = os.getenv("ENABLE_BOARD_HHPANDA", "True").lower() == "true"
    ENABLE_BOARD_MOVIESDRIVE = os.getenv("ENABLE_BOARD_MOVIESDRIVE", "True").lower() == "true"
    ENABLE_BOARD_HDHUB4U = os.getenv("ENABLE_BOARD_HDHUB4U", "True").lower() == "true"
    ENABLE_BOARD_UHDMOVIES = os.getenv("ENABLE_BOARD_UHDMOVIES", "True").lower() == "true"
    ENABLE_BOARD_4KHDHUB = os.getenv("ENABLE_BOARD_4KHDHUB", "True").lower() == "true"
    ENABLE_BOARD_TOPXX = os.getenv("ENABLE_BOARD_TOPXX", "False").lower() == "true"
    ENABLE_BOARD_HDTODAY = os.getenv("ENABLE_BOARD_HDTODAY", "True").lower() == "true"
    ENABLE_BOARD_VIDKING = os.getenv("ENABLE_BOARD_VIDKING", "True").lower() == "true"
    ENABLE_BOARD_ERNAX = os.getenv("ENABLE_BOARD_ERNAX", "True").lower() == "true"
    ENABLE_BOARD_FILM4K_TV = os.getenv("ENABLE_BOARD_FILM4K_TV", "True").lower() == "true"
    ENABLE_BOARD_IPTV = os.getenv("ENABLE_BOARD_IPTV", os.getenv("ENABLE_BOARD_IPTV_ORG", "True")).lower() == "true"
    ENABLE_BOARD_MOVIES2WATCH = os.getenv("ENABLE_BOARD_MOVIES2WATCH", "True").lower() == "true"

    # Subtitle timing.
    # Positive shifts subtitles later, negative shows them earlier.
    # Used by subtitle_utils when building SRT/VTT output.
    SUBTITLE_TIME_OFFSET = _env_float("SUBTITLE_TIME_OFFSET", 0.0)

    # Progressive VTT flow (sync_vtt_service).
    # The first slice of the film is translated inline and returned right away,
    # the rest is translated in the background.
    # SYNC_VTT_HEAD_SECONDS: how many seconds of the film to translate inline.
    SYNC_VTT_HEAD_SECONDS = _env_float("SYNC_VTT_HEAD_SECONDS", 300.0)
    # SYNC_VTT_HEAD_MAX_BLOCKS: hard cap on the inline batch, protects dense subs.
    SYNC_VTT_HEAD_MAX_BLOCKS = _env_int("SYNC_VTT_HEAD_MAX_BLOCKS", 400)
    # SYNC_VTT_BACKGROUND_SLICE: cue count per background chunk.
    SYNC_VTT_BACKGROUND_SLICE = _env_int("SYNC_VTT_BACKGROUND_SLICE", 150)

    API_ID = os.getenv("API_ID")
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    USER_SESSION_STRING = os.getenv("USER_SESSION_STRING", "")
    EXTRA_SESSION_STRINGS = os.getenv("EXTRA_SESSION_STRINGS", "")
    EXTRA_BOT_TOKENS = os.getenv("EXTRA_BOT_TOKENS", "")
    MEDIA_SESSIONS_PER_DC = _env_int("MEDIA_SESSIONS_PER_DC", 3)

    TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
    LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")

    @classmethod
    def validate(cls) -> bool:
        if not getattr(cls, "ENABLE_SOURCE_TELEGRAM", True):
            return False

        missing = []
        if not cls.API_ID:
            missing.append("API_ID")
        if not cls.API_HASH:
            missing.append("API_HASH")
        if not cls.BOT_TOKEN and not cls.USER_SESSION_STRING:
            missing.append("BOT_TOKEN or USER_SESSION_STRING")
        if not cls.TELEGRAM_CHANNEL_ID:
            missing.append("TELEGRAM_CHANNEL_ID")

        if missing:
            return False

        try:
            cls.API_ID = int(cls.API_ID)
        except (ValueError, TypeError):
            return False

        if cls.TELEGRAM_CHANNEL_ID and isinstance(cls.TELEGRAM_CHANNEL_ID, str):
            val = cls.TELEGRAM_CHANNEL_ID.strip()
            if val.startswith("-") or val.isdigit():
                try:
                    cls.TELEGRAM_CHANNEL_ID = int(val)
                except ValueError:
                    pass

        if cls.LOG_CHANNEL_ID and isinstance(cls.LOG_CHANNEL_ID, str):
            val = cls.LOG_CHANNEL_ID.strip()
            if val.startswith("-") or val.isdigit():
                try:
                    cls.LOG_CHANNEL_ID = int(val)
                except ValueError:
                    pass
        return True
