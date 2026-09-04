"""Qobuz-TG: /al_id /ar_id /tr_id → download → poster + music → delete.

Uses TELEGRAM_API + TELEGRAM_HASH (Pyrogram), optional USER_SESSION_STRING
for larger uploads (MLTB-style).
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from pyrogram import Client, filters, idle
from pyrogram.types import Message

from bot.db import merge_config, save_to_mongo
from bot.poster import caption_from_album_meta, find_cover
from bot.qobuz_worker import cleanup, meta_from_folder, run_download

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("qobuz-tg")

PLAIN_RE = re.compile(
    r"^(?P<kind>al|ar|tr)[-_]?id\s+(?P<id>[A-Za-z0-9]+)\s*$",
    re.I,
)

AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".wav", ".ogg"}


def _load_config():
    try:
        import config as cfg  # type: ignore
    except ImportError as e:
        raise SystemExit(
            "Missing config.py — copy config_sample.py to config.py and edit it."
        ) from e
    return merge_config(cfg)


def _allowed(user_id: int, cfg) -> bool:
    owners = {int(cfg.OWNER_ID)}
    extra = getattr(cfg, "AUTHORIZED_IDS", []) or []
    owners.update(int(x) for x in extra if x)
    return int(user_id) in owners


def _max_bytes(cfg) -> int:
    mb = float(getattr(cfg, "MAX_TG_FILE_MB", 49))
    return int(mb * 1024 * 1024)


def _list_audio(album_dir: Path) -> list[Path]:
    return [
        p
        for p in sorted(album_dir.iterdir())
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    ]


async def _send_tracks(
    client: Client,
    user_client: Client | None,
    chat_id: int,
    files: list[Path],
    cfg,
    status: Message,
) -> tuple[int, int]:
    sent, skipped = 0, 0
    limit = _max_bytes(cfg)

    for i, path in enumerate(files, 1):
        size = path.stat().st_size
        use_user = user_client is not None and size > limit
        sender = user_client if use_user else client
        effective_limit = (2 * 1024 * 1024 * 1024) if use_user else limit

        if size > effective_limit:
            skipped += 1
            log.warning("Skip %s (%.1f MB > limit)", path.name, size / 1024 / 1024)
            continue

        try:
            await status.edit_text(f"🎵 Uploading {i}/{len(files)}: {path.name}")
        except Exception:
            pass

        try:
            if path.suffix.lower() == ".mp3":
                await sender.send_audio(chat_id, path, file_name=path.name)
            else:
                await sender.send_document(chat_id, path, file_name=path.name)
            sent += 1
            await asyncio.sleep(0.4)
        except Exception as e:
            log.error("Upload failed %s: %s", path.name, e)
            skipped += 1

    return sent, skipped


async def _run_job(client: Client, message: Message, kind: str, id_: str, cfg, user_client):
    if not message.from_user or not _allowed(message.from_user.id, cfg):
        await message.reply_text("Unauthorized.")
        return

    status = await message.reply_text(f"⏳ {kind} `{id_}` — starting…")
    job_dir: Path | None = None

    try:
        await status.edit_text(f"⬇️ Downloading {kind} `{id_}`…")
        job_dir, album_dirs = await asyncio.to_thread(run_download, kind, id_, cfg)

        if not album_dirs:
            await status.edit_text("Download finished but no album folder found.")
            return

        channel = int(cfg.CHANNEL_ID)
        total_sent = total_skip = posted = 0

        for album_dir in album_dirs:
            meta = meta_from_folder(album_dir)
            caption = caption_from_album_meta(meta)
            cover = find_cover(album_dir)

            await status.edit_text(f"📤 Poster: {meta.get('title') or album_dir.name}")

            if cover and cover.is_file():
                await client.send_photo(channel, cover, caption=caption[:1024])
            else:
                await client.send_message(channel, caption)

            posted += 1

            if getattr(cfg, "SEND_TRACKS", True):
                files = _list_audio(album_dir)
                s, k = await _send_tracks(
                    client, user_client, channel, files, cfg, status
                )
                total_sent += s
                total_skip += k

        await status.edit_text(
            f"✅ Done\n"
            f"Posters: {posted}\n"
            f"Tracks sent: {total_sent}\n"
            f"Skipped: {total_skip}\n"
            f"Local files deleted."
        )
    except Exception as exc:
        log.exception("job failed")
        try:
            await status.edit_text(f"❌ Error:\n{exc}")
        except Exception:
            await message.reply_text(f"❌ Error:\n{exc}")
    finally:
        if job_dir and getattr(cfg, "DELETE_AFTER_POST", True):
            cleanup(job_dir)


def main() -> None:
    cfg = _load_config()

    api_id = int(cfg.TELEGRAM_API)
    api_hash = str(cfg.TELEGRAM_HASH)
    bot_token = str(cfg.BOT_TOKEN)
    sessions = Path(getattr(cfg, "TEMP_DIR", "/tmp/qobuz-tg")) / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)

    app = Client(
        "qobuz_tg_bot",
        api_id=api_id,
        api_hash=api_hash,
        bot_token=bot_token,
        workdir=str(sessions),
    )

    user_client = None
    session = getattr(cfg, "USER_SESSION_STRING", "") or ""
    if session.strip():
        user_client = Client(
            "qobuz_tg_user",
            api_id=api_id,
            api_hash=api_hash,
            session_string=session.strip(),
            workdir=str(sessions),
        )

    @app.on_message(filters.command(["start", "help"]))
    async def cmd_start(_, message: Message):
        if not message.from_user or not _allowed(message.from_user.id, cfg):
            await message.reply_text("Unauthorized.")
            return
        await message.reply_text(
            "**Qobuz-TG**\n\n"
            "`/al_id <album_id>`\n"
            "`/ar_id <artist_id>`\n"
            "`/tr_id <track_id>`\n\n"
            "Or: `al-id 123` / `ar-id 123` / `tr-id 123`\n\n"
            "Flow: download → poster + music → delete local files.\n"
            "`/save_config` — push current config to MongoDB",
            quote=True,
        )

    @app.on_message(filters.command("al_id"))
    async def cmd_al(_, message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.reply_text("Usage: /al_id <album_id>")
            return
        await _run_job(app, message, "album", parts[1].strip(), cfg, user_client)

    @app.on_message(filters.command("ar_id"))
    async def cmd_ar(_, message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.reply_text("Usage: /ar_id <artist_id>")
            return
        await _run_job(app, message, "artist", parts[1].strip(), cfg, user_client)

    @app.on_message(filters.command("tr_id"))
    async def cmd_tr(_, message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.reply_text("Usage: /tr_id <track_id>")
            return
        await _run_job(app, message, "track", parts[1].strip(), cfg, user_client)

    @app.on_message(filters.command("save_config"))
    async def cmd_save(_, message: Message):
        if not message.from_user or not _allowed(message.from_user.id, cfg):
            await message.reply_text("Unauthorized.")
            return
        data = {k: getattr(cfg, k) for k in dir(cfg) if k.isupper()}
        ok = save_to_mongo(getattr(cfg, "DATABASE_URL", ""), cfg.BOT_TOKEN, data)
        await message.reply_text(
            "Saved to MongoDB." if ok else "MongoDB save failed / no DATABASE_URL."
        )

    @app.on_message(
        filters.text
        & ~filters.command(["start", "help", "al_id", "ar_id", "tr_id", "save_config"])
    )
    async def plain(_, message: Message):
        text = (message.text or "").strip()
        m = PLAIN_RE.match(text)
        if not m:
            return
        kind_map = {"al": "album", "ar": "artist", "tr": "track"}
        await _run_job(
            app,
            message,
            kind_map[m.group("kind").lower()],
            m.group("id"),
            cfg,
            user_client,
        )

    log.info("Qobuz-TG starting (Pyrogram)…")

    async def runner():
        await app.start()
        if user_client:
            await user_client.start()
            log.info("User session started (large uploads enabled)")
        me = await app.get_me()
        log.info("Bot @%s", me.username)
        await idle()
        await app.stop()
        if user_client:
            await user_client.stop()

    app.run(runner())


if __name__ == "__main__":
    main()
