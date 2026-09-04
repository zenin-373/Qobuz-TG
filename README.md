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

## Deploy to Heroku (GitHub Actions)

Files:

- `heroku.yml` — worker process
- `Procfile` — `worker: python update.py; python -m bot`
- `.github/workflows/deploy-heroku.yml` — deploy on push to `main`

### 1. GitHub secrets

Repo → **Settings → Secrets and variables → Actions**:

| Secret | Value |
|--------|--------|
| `HEROKU_API_KEY` | Heroku Account → API Key |
| `HEROKU_EMAIL` | Heroku login email |
| `HEROKU_APP_NAME` | Your app name (e.g. `qobuz-tg-bot`) |

### 2. Heroku Config Vars

App → **Settings → Config Vars** (required):

```text
BOT_TOKEN
OWNER_ID
CHANNEL_ID
TELEGRAM_API
TELEGRAM_HASH
QOBUZ_APP_ID
QOBUZ_SECRET
QOBUZ_AUTH_TOKENS          # comma-separated tokens
DATABASE_URL               # optional MongoDB
SEND_TRACKS=true
DELETE_AFTER_POST=true
QUALITY=hi-res-192
```

### 3. Deploy

- Push to `main`, or
- **Actions → Deploy to Heroku → Run workflow**

Worker dyno is scaled to `1` (no web dyno).

### Manual Heroku CLI

```bash
heroku create your-app-name
heroku buildpacks:set heroku/python
git push heroku main
heroku ps:scale worker=1 web=0
heroku config:set BOT_TOKEN=... TELEGRAM_API=... # etc
```

## Config (local)

Copy `config_sample.py` → `config.py` or use env vars (Heroku).

| Variable | Source |
|----------|--------|
| `BOT_TOKEN` | @BotFather |
| `TELEGRAM_API` / `TELEGRAM_HASH` | [my.telegram.org](https://my.telegram.org) |
| `OWNER_ID` / `CHANNEL_ID` | Telegram ids |
| `DATABASE_URL` | MongoDB |
| `QOBUZ_*` | app_id, secret, tokens |

## Update

```bash
python update.py
```

## Local setup

```bash
git clone https://github.com/zenin-373/Qobuz-TG.git
cd Qobuz-TG
pip install -r requirements.txt
pip install git+https://github.com/zenin-373/qobuzdl-collab.git
cp config_sample.py config.py
python -m bot
```

## License

MIT
