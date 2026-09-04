# Qobuz-TG

Telegram bot for Qobuz: download by ID → post album **poster** to your channel → **delete** local files.

Nothing is kept on the server.

## Commands

Telegram command names cannot contain `-`, so use underscores:

| Command | Meaning |
|---------|--------|
| `/al_id <id>` | Download album |
| `/ar_id <id>` | Download full artist discography |
| `/tr_id <id>` | Download single track |

Examples:

```text
/al_id 0074643811224
/ar_id 687008
/tr_id 23929921
```

You can also send plain text:

```text
al-id 0074643811224
ar-id 687008
tr-id 23929921
```

## Pipeline

```text
command → Qobuz download (temp)
       → post cover + caption to channel
       → delete temp files
       → done
```

### Poster caption

```text
📖 Album Title
🎤 Artist: ...
📅 Year: ...
🎵 Tracks: ...
🎧 Quality: ...
🏷️ Genre: ...
```

## Requirements

- Python 3.10+
- Telegram bot token (@BotFather)
- Your Telegram user id (owner)
- Channel id (bot must be admin)
- Qobuz `app_id`, `secret`, `auth_token`(s)
- [qobuzdl-collab](https://github.com/zenin-373/qobuzdl-collab) / qobuz-dl installed

## Setup

```bash
git clone https://github.com/zenin-373/Qobuz-TG.git
cd Qobuz-TG
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Install Qobuz downloader
pip install git+https://github.com/zenin-373/qobuzdl-collab.git

cp config_sample.py config.py
# edit config.py

python -m bot
```

## Config (`config.py`)

See `config_sample.py`.

| Key | Description |
|-----|-------------|
| `BOT_TOKEN` | From @BotFather |
| `OWNER_ID` | Your numeric Telegram user id |
| `CHANNEL_ID` | Channel to post posters (e.g. `-100...`) |
| `QOBUZ_APP_ID` | Qobuz app id |
| `QOBUZ_SECRET` | Qobuz secret |
| `QOBUZ_AUTH_TOKENS` | List of tokens |
| `TEMP_DIR` | Temp download folder |
| `QUALITY` | `hi-res-192` / `hi-res` / `cd` |

## Notes

- Local files are **always deleted** after the poster is sent.
- Full Hi-Res tracks often exceed Telegram’s ~50 MB bot limit; this bot posts the **poster only** by default.
- Drive upload is **not** included.

## License

MIT
