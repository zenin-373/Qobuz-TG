# Copy to config.py and fill in values.

# Telegram
BOT_TOKEN = "123456:ABC..."  # @BotFather
OWNER_ID = 0  # your numeric user id (get from @userinfobot)
CHANNEL_ID = -1001234567890  # channel where posters are sent (bot must be admin)

# Only OWNER_ID can use the bot (add more ids if needed)
AUTHORIZED_IDS = [
    # OWNER_ID is always allowed
]

# Qobuz (use app_id/secret matching your token version)
QOBUZ_APP_ID = "798273057"
QOBUZ_SECRET = "abb21364945c0583309667d13ca3d93a"
QOBUZ_AUTH_TOKENS = [
    "PASTE_TOKEN_HERE",
    # "TOKEN_2",
]

# Download
TEMP_DIR = "/tmp/qobuz-tg"
QUALITY = "hi-res-192"  # hi-res-192 | hi-res | cd | mp3
FOLDER_TEMPLATE = "{main_artist}/{album} - {year} [{quality}]"
TRACK_TEMPLATE = "{title}"

# Behaviour
DELETE_AFTER_POST = True  # always wipe local files after poster
SEND_TRACKS = False  # True = try upload audio under Telegram size limit (usually skip hi-res)
