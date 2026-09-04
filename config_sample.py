# Copy to config.py and fill in values.

# ── Telegram (same style as Aeon-MLTB) ───────────────────────────
BOT_TOKEN = "123456:ABC..."  # @BotFather
OWNER_ID = 0  # numeric id (@userinfobot)
CHANNEL_ID = -1001234567890  # bot must be admin

# From https://my.telegram.org → API development tools
TELEGRAM_API = 12345678  # api_id (int)
TELEGRAM_HASH = "your_api_hash"

# Optional: Pyrogram session string for large file uploads (>~50MB).
# Generate with a small pyrogram script / use premium account.
USER_SESSION_STRING = ""

AUTHORIZED_IDS = [
    # extra allowed user ids
]

# MongoDB — stores credentials / settings (optional but recommended)
# Example: mongodb+srv://user:pass@cluster.mongodb.net/qobuz_tg
DATABASE_URL = ""

# Auto-update (update.py)
UPSTREAM_REPO = "https://github.com/zenin-373/Qobuz-TG"
UPSTREAM_BRANCH = "main"

# ── Qobuz ────────────────────────────────────────────────────────
QOBUZ_APP_ID = "798273057"
QOBUZ_SECRET = "abb21364945c0583309667d13ca3d93a"
QOBUZ_AUTH_TOKENS = [
    "PASTE_TOKEN_HERE",
    # "TOKEN_2",
]

# ── Download ─────────────────────────────────────────────────────
TEMP_DIR = "/tmp/qobuz-tg"
QUALITY = "hi-res-192"  # hi-res-192 | hi-res | cd | mp3
FOLDER_TEMPLATE = "{main_artist}/{album} - {year} [{quality}]"
TRACK_TEMPLATE = "{title}"
DOWNLOAD_TIMEOUT = 7200  # seconds

# ── Behaviour ────────────────────────────────────────────────────
DELETE_AFTER_POST = True  # wipe local files after upload
SEND_TRACKS = True  # send music files to the channel
MAX_TG_FILE_MB = 49  # bot-api safe limit; user session can exceed this
