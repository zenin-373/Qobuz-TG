"""Qobuz-TG bot: /al_id /ar_id /tr_id → download → poster → delete."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.poster import caption_from_album_meta, find_cover
from bot.qobuz_worker import cleanup, meta_from_folder, run_download

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("qobuz-tg")

# plain-text: al-id 123 / ar-id 123 / tr-id 123
PLAIN_RE = re.compile(
    r"^(?P<kind>al|ar|tr)[-_]?id\s+(?P<id>[A-Za-z0-9]+)\s*$",
    re.I,
)


def _load_config():
    try:
        import config as cfg  # type: ignore
    except ImportError as e:
        raise SystemExit(
            "Missing config.py — copy config_sample.py to config.py and edit it."
        ) from e
    return cfg


def _allowed(user_id: int, cfg) -> bool:
    owners = {int(cfg.OWNER_ID)}
    extra = getattr(cfg, "AUTHORIZED_IDS", []) or []
    owners.update(int(x) for x in extra if x)
    return user_id in owners


async def _deny(update: Update) -> None:
    if update.effective_message:
        await update.effective_message.reply_text("Unauthorized.")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["cfg"]
    if not update.effective_user or not _allowed(update.effective_user.id, cfg):
        await _deny(update)
        return
    await update.effective_message.reply_text(
        "Qobuz-TG\n\n"
        "/al_id <album_id>\n"
        "/ar_id <artist_id>\n"
        "/tr_id <track_id>\n\n"
        "Or send: al-id 123 / ar-id 123 / tr-id 123\n\n"
        "Flow: download → post poster to channel → delete local files."
    )


async def _run_job(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    kind: str,
    id_: str,
) -> None:
    cfg = context.application.bot_data["cfg"]
    if not update.effective_user or not _allowed(update.effective_user.id, cfg):
        await _deny(update)
        return

    msg = update.effective_message
    status = await msg.reply_text(f"⏳ {kind} `{id_}` — starting…", parse_mode="Markdown")

    job_dir: Path | None = None
    try:
        await status.edit_text(f"⬇️ Downloading {kind} `{id_}`…", parse_mode="Markdown")
        job_dir, album_dirs = run_download(kind, id_, cfg)

        if not album_dirs:
            await status.edit_text("Download finished but no album folder found.")
            return

        channel = int(cfg.CHANNEL_ID)
        posted = 0
        for album_dir in album_dirs:
            meta = meta_from_folder(album_dir)
            caption = caption_from_album_meta(meta)
            cover = find_cover(album_dir)

            await status.edit_text(
                f"📤 Posting: {meta.get('title') or album_dir.name}"
            )

            if cover and cover.is_file():
                with cover.open("rb") as f:
                    await context.bot.send_photo(
                        chat_id=channel,
                        photo=f,
                        caption=caption[:1024],
                    )
            else:
                await context.bot.send_message(chat_id=channel, text=caption)

            posted += 1

        await status.edit_text(f"✅ Done — posted {posted} poster(s). Local files deleted.")
    except Exception as exc:
        log.exception("job failed")
        await status.edit_text(f"❌ Error:\n{exc}")
    finally:
        if job_dir and getattr(cfg, "DELETE_AFTER_POST", True):
            cleanup(job_dir)


async def cmd_al_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Usage: /al_id <album_id>")
        return
    await _run_job(update, context, "album", context.args[0])


async def cmd_ar_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Usage: /ar_id <artist_id>")
        return
    await _run_job(update, context, "artist", context.args[0])


async def cmd_tr_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Usage: /tr_id <track_id>")
        return
    await _run_job(update, context, "track", context.args[0])


async def plain_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.effective_message.text or "").strip()
    m = PLAIN_RE.match(text)
    if not m:
        return
    kind_map = {"al": "album", "ar": "artist", "tr": "track"}
    await _run_job(update, context, kind_map[m.group("kind").lower()], m.group("id"))


def main() -> None:
    cfg = _load_config()
    app = (
        Application.builder()
        .token(cfg.BOT_TOKEN)
        .concurrent_updates(False)
        .build()
    )
    app.bot_data["cfg"] = cfg

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("al_id", cmd_al_id))
    app.add_handler(CommandHandler("ar_id", cmd_ar_id))
    app.add_handler(CommandHandler("tr_id", cmd_tr_id))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, plain_text))

    log.info("Qobuz-TG starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
