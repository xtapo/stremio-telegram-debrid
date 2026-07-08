import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class Config:
    PORT = int(os.getenv("PORT", 7860))
    ADDON_URL = os.getenv("ADDON_URL", f"http://localhost:{PORT}").rstrip("/")
    API_KEY = os.getenv("API_KEY", "")
    CACHE_TTL = int(os.getenv("CACHE_TTL", 1800))
    TIMEZONE = os.getenv("TIMEZONE", "UTC")
    STREAM_CACHE_SIZE_MB = int(os.getenv("STREAM_CACHE_SIZE_MB", 256))
    PREFETCH_CHUNKS = int(os.getenv("PREFETCH_CHUNKS", 3))
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
    AUTO_VIET_SUB = os.getenv("AUTO_VIET_SUB", "True").lower() == "true"
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

    API_ID = os.getenv("API_ID")
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    USER_SESSION_STRING = os.getenv("USER_SESSION_STRING", "")

    TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
    LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")

    @classmethod
    def validate(cls):
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
            raise ValueError(
                f"Missing critical configuration variables: {', '.join(missing)}. "
                "Please configure them in your environment or a .env file."
            )

        try:
            cls.API_ID = int(cls.API_ID)
        except (ValueError, TypeError):
            raise ValueError("API_ID must be a valid integer.")

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
