# Qobuz-TG

Telegram bot for Qobuz (MLTB-style):

**download → post cover + caption + music files → delete local files**

## Commands

| Command | Action |
|---------|--------|
| `/al_id <id>` | Album |
| `/ar_id <id>` | Artist discography |
| `/tr_id <id>` | Track |
| `/save_config` | Save settings to MongoDB |

Plain text also works: `al-id 123`, `ar-id 123`, `tr-id 123`.

## Pipeline

```text
/al_id …
  → qobuz-dl download (temp)
  → send cover + caption to channel
  → send each track (audio/document)
  → delete temp files
```

Poster caption:

```text
📖 Album Title
🎤 Artist: ...
📅 Year: ...
🎵 Tracks: ...
🎧 Quality: ...
🏷️ Genre: ...
```

## Config (Aeon-MLTB style)

Copy `config_sample.py` → `config.py`:

| Variable | Source |
|----------|--------|
| `BOT_TOKEN` | @BotFather |
| `OWNER_ID` | @userinfobot |
| `CHANNEL_ID` | your channel (`-100…`), bot = admin |
| `TELEGRAM_API` | [my.telegram.org](https://my.telegram.org) api_id |
| `TELEGRAM_HASH` | my.telegram.org api_hash |
| `USER_SESSION_STRING` | optional — large FLAC uploads |
| `DATABASE_URL` | MongoDB URI (store credentials) |
| `QOBUZ_*` | app_id, secret, tokens |

`SEND_TRACKS = True` by default.

### File size

- **Bot only:** ~50 MB per file (`MAX_TG_FILE_MB = 49`)
- **With `USER_SESSION_STRING`:** larger files via user client (Premium helps)

Hi-Res FLACs often need the user session or lower quality (`cd` / `hi-res`).

## MongoDB

Set `DATABASE_URL`. On start, settings override `config.py` when present in DB.

Send `/save_config` as owner to push current config into MongoDB.

## Update to latest commit

```bash
python update.py
```

Pulls `UPSTREAM_REPO` / `UPSTREAM_BRANCH` (keeps local `config.py`).

## Setup

```bash
git clone https://github.com/zenin-373/Qobuz-TG.git
cd Qobuz-TG
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install git+https://github.com/zenin-373/qobuzdl-collab.git

cp config_sample.py config.py
# fill BOT_TOKEN, TELEGRAM_API, TELEGRAM_HASH, OWNER_ID, CHANNEL_ID, Qobuz tokens

python -m bot
```

Optional auto-update before start:

```bash
python update.py && python -m bot
```

## License

MIT
