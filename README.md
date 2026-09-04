# Qobuz-TG

Telegram bot for Qobuz (MLTB-style):

**download → post cover + caption + music files → delete local files**

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/zenin-373/Qobuz-TG/blob/main/qobuz_tg_colab.ipynb)

## Colab (easiest deploy)

Notebook: [`qobuz_tg_colab.ipynb`](https://github.com/zenin-373/Qobuz-TG/blob/main/qobuz_tg_colab.ipynb)

1. Open in Colab (badge above)
2. Fill form: Telegram + Qobuz + Heroku
3. Run **Deploy to Heroku** cell

Sets config vars, pushes code, scales `worker=1`.

## Commands

| Command | Action |
|---------|--------|
| `/al_id <id>` | Album |
| `/ar_id <id>` | Artist discography |
| `/tr_id <id>` | Track |
| `/qobuz` / `/qobuz_add` / `/qobuz_del` | Manage Qobuz tokens |
| `/save_config` | Save settings to MongoDB |

## Pipeline

```text
/al_id …
  → qobuz-dl download (temp)
  → send cover + caption to channel
  → send each track
  → delete temp files
```

## Deploy (GitHub Actions form)

**Actions → Deploy to Heroku** (`deploy.yml`) → **Run workflow** → fill inputs.

## Config vars (Heroku)

```text
BOT_TOKEN, OWNER_ID, CHANNEL_ID
TELEGRAM_API, TELEGRAM_HASH
QOBUZ_APP_ID, QOBUZ_SECRET, QOBUZ_AUTH_TOKENS
DATABASE_URL (optional)
SEND_TRACKS=true, DELETE_AFTER_POST=true, QUALITY=hi-res-192
```

## Local

```bash
git clone https://github.com/zenin-373/Qobuz-TG.git
cd Qobuz-TG
pip install -r requirements.txt
cp config_sample.py config.py
python -m bot
```

## License

MIT
