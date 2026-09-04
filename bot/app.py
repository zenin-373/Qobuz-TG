"""Qobuz-TG: download → poster + music → delete.

Uses wzgram (Pyrogram fork) over MTProto — same idea as Aeon:
bot token alone can upload up to ~2 GB (no USER_SESSION_STRING required).
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

try:
    from wzgram import Client, filters, idle
    from wzgram.types import Message
except ImportError:  # fallback if only pyrogram installed
    from pyrogram import Client, filters, idle
    from pyrogram.types import Message

from bot.db import (
    add_token,
    del_token,
    list_tokens,
    mask_token,
    merge_config,
    persist_cfg,
    save_to_mongo,
    set_app_creds,
)
from bot.env_config import load_config
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

# MTProto bot/user limit (Aeon / Pyrogram / wzgram style — NOT HTTP Bot API 50MB)
UPLOAD_LIMIT = 2 * 1024 * 1024 * 1024  # 2 GB

CMD_BLOCK = [
    "start",
    "help",
    "al_id",
    "ar_id",
    "tr_id",
    "save_config",
    "qobuz",
    "qobuz_list",
    "qobuz_add",
    "qobuz_del",
    "qobuz_setapp",
    "qobuz_quality",
]


def _load_config():
    return merge_config(load_config())


def _allowed(user_id: int, cfg) -> bool:
    owners = {int(cfg.OWNER_ID)}
    extra = getattr(cfg, "AUTHORIZED_IDS", []) or []
    owners.update(int(x) for x in extra if x)
    return int(user_id) in owners


def _list_audio(album_dir: Path) -> list[Path]:
    return [
        p
        for p in sorted(album_dir.iterdir())
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    ]


async def _send_tracks(client, user_client, chat_id, files, cfg, status):
    """Upload via MTProto. Bot client alone supports ~2GB (like Aeon without session)."""
    sent, skipped = 0, 0
    # Prefer user client if present; otherwise bot MTProto (2GB)
    sender = user_client if user_client is not None else client
    mode = "user/2GB" if user_client is not None else "bot/MTProto/2GB"
    log.info("Upload mode: %s (%d files)", mode, len(files))

    for i, path in enumerate(files, 1):
        size = path.stat().st_size
        if size > UPLOAD_LIMIT:
            skipped += 1
            log.warning("Skip %s (%.1f MB > 2GB)", path.name, size / 1024 / 1024)
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
            await asyncio.sleep(0.3)
        except Exception as e:
            log.error("Upload failed %s: %s", path.name, e)
            skipped += 1
    return sent, skipped


async def _run_job(client, message, kind, id_, cfg, user_client):
    if not message.from_user or not _allowed(message.from_user.id, cfg):
        await message.reply_text("Unauthorized.")
        return

    status = await message.reply_text(f"⏳ {kind} `{id_}` — starting…")
    job_dir = None
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
                s, k = await _send_tracks(
                    client, user_client, channel, _list_audio(album_dir), cfg, status
                )
                total_sent += s
                total_skip += k

        await status.edit_text(
            f"✅ Done (MTProto ~2GB)\nPosters: {posted}\nTracks sent: {total_sent}\n"
            f"Skipped: {total_skip}\nLocal files deleted."
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
    sessions = Path(getattr(cfg, "TEMP_DIR", "/tmp/qobuz-tg")) / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)

    app = Client(
        "qobuz_tg_bot",
        api_id=api_id,
        api_hash=api_hash,
        bot_token=str(cfg.BOT_TOKEN),
        workdir=str(sessions),
    )

    user_client = None
    us = getattr(cfg, "USER_SESSION_STRING", "") or ""
    if us.strip():
        user_client = Client(
            "qobuz_tg_user",
            api_id=api_id,
            api_hash=api_hash,
            session_string=us.strip(),
            workdir=str(sessions),
        )

    @app.on_message(filters.command(["start", "help"]))
    async def cmd_start(_, message: Message):
        if not message.from_user or not _allowed(message.from_user.id, cfg):
            await message.reply_text("Unauthorized.")
            return
        await message.reply_text(
            "**Qobuz-TG** (wzgram/MTProto · ~2GB uploads)\n\n"
            "**Download**\n"
            "`/al_id <id>` `/ar_id <id>` `/tr_id <id>`\n\n"
            "**Qobuz**\n"
            "`/qobuz` `/qobuz_list` `/qobuz_add` `/qobuz_del`\n"
            "`/qobuz_setapp` `/qobuz_quality` `/save_config`\n\n"
            "No USER_SESSION_STRING needed for 2GB (same as Aeon).",
            quote=True,
        )

    @app.on_message(filters.command("al_id"))
    async def cmd_al(_, message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            return await message.reply_text("Usage: /al_id <album_id>")
        await _run_job(app, message, "album", parts[1].strip(), cfg, user_client)

    @app.on_message(filters.command("ar_id"))
    async def cmd_ar(_, message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            return await message.reply_text("Usage: /ar_id <artist_id>")
        await _run_job(app, message, "artist", parts[1].strip(), cfg, user_client)

    @app.on_message(filters.command("tr_id"))
    async def cmd_tr(_, message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            return await message.reply_text("Usage: /tr_id <track_id>")
        await _run_job(app, message, "track", parts[1].strip(), cfg, user_client)

    @app.on_message(filters.command("qobuz"))
    async def cmd_qobuz(_, message: Message):
        if not message.from_user or not _allowed(message.from_user.id, cfg):
            return await message.reply_text("Unauthorized.")
        toks = list_tokens(cfg)
        await message.reply_text(
            f"**Qobuz setup**\n"
            f"app_id: `{getattr(cfg, 'QOBUZ_APP_ID', '')}`\n"
            f"secret: `{mask_token(str(getattr(cfg, 'QOBUZ_SECRET', '')))}`\n"
            f"tokens: **{len(toks)}**\n"
            f"quality: `{getattr(cfg, 'QUALITY', '')}`\n"
            f"upload: `MTProto ~2GB`\n"
            f"mongo: `{'yes' if getattr(cfg, 'DATABASE_URL', '') else 'no'}`"
        )

    @app.on_message(filters.command("qobuz_list"))
    async def cmd_qobuz_list(_, message: Message):
        if not message.from_user or not _allowed(message.from_user.id, cfg):
            return await message.reply_text("Unauthorized.")
        toks = list_tokens(cfg)
        if not toks:
            return await message.reply_text("No tokens. Add with `/qobuz_add <token>`")
        lines = [f"{i}. `{mask_token(t)}`" for i, t in enumerate(toks, 1)]
        await message.reply_text("**Tokens**\n" + "\n".join(lines))

    @app.on_message(filters.command("qobuz_add"))
    async def cmd_qobuz_add(_, message: Message):
        if not message.from_user or not _allowed(message.from_user.id, cfg):
            return await message.reply_text("Unauthorized.")
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            return await message.reply_text("Usage: /qobuz_add <auth_token>")
        n = add_token(cfg, parts[1].strip())
        await message.reply_text(f"✅ Token added. Total: {n}")

    @app.on_message(filters.command("qobuz_del"))
    async def cmd_qobuz_del(_, message: Message):
        if not message.from_user or not _allowed(message.from_user.id, cfg):
            return await message.reply_text("Unauthorized.")
        parts = (message.text or "").split()
        if len(parts) < 2 or not parts[1].isdigit():
            return await message.reply_text("Usage: /qobuz_del <number>")
        ok = del_token(cfg, int(parts[1]))
        await message.reply_text("✅ Removed." if ok else "❌ Invalid index.")

    @app.on_message(filters.command("qobuz_setapp"))
    async def cmd_qobuz_setapp(_, message: Message):
        if not message.from_user or not _allowed(message.from_user.id, cfg):
            return await message.reply_text("Unauthorized.")
        parts = (message.text or "").split()
        if len(parts) < 3:
            return await message.reply_text("Usage: /qobuz_setapp <app_id> <secret>")
        set_app_creds(cfg, parts[1], parts[2])
        await message.reply_text("✅ app_id + secret updated.")

    @app.on_message(filters.command("qobuz_quality"))
    async def cmd_qobuz_quality(_, message: Message):
        if not message.from_user or not _allowed(message.from_user.id, cfg):
            return await message.reply_text("Unauthorized.")
        parts = (message.text or "").split()
        allowed = {"hi-res-192", "hi-res", "cd", "mp3"}
        if len(parts) < 2 or parts[1] not in allowed:
            return await message.reply_text(
                "Usage: /qobuz_quality <hi-res-192|hi-res|cd|mp3>"
            )
        cfg.QUALITY = parts[1]
        persist_cfg(cfg)
        await message.reply_text(f"✅ Quality set to `{parts[1]}`")

    @app.on_message(filters.command("save_config"))
    async def cmd_save(_, message: Message):
        if not message.from_user or not _allowed(message.from_user.id, cfg):
            return await message.reply_text("Unauthorized.")
        ok = persist_cfg(cfg)
        await message.reply_text(
            "Saved to MongoDB." if ok else "Failed — set DATABASE_URL."
        )

    @app.on_message(filters.text & ~filters.command(CMD_BLOCK))
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

    log.info("Qobuz-TG starting (wzgram/MTProto)…")

    async def runner():
        await app.start()
        if user_client:
            await user_client.start()
            log.info("User session started")
        log.info("Bot MTProto uploads enabled (~2GB, no session string required)")
        me = await app.get_me()
        log.info("Bot @%s", me.username)
        await idle()
        await app.stop()
        if user_client:
            await user_client.stop()

    app.run(runner())


if __name__ == "__main__":
    main()
