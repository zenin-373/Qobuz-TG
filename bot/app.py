"""Qobuz-TG: info → download → progress upload → delete."""

from __future__ import annotations

import asyncio
import logging
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from wzgram import Client, enums, filters, idle
    from wzgram.errors import FloodWait
    from wzgram.types import Message

    log_lib = "wzgram"
except ImportError:
    from pyrogram import Client, enums, filters, idle
    from pyrogram.errors import FloodWait
    from pyrogram.types import Message

    log_lib = "pyrogram"

from bot.db import (
    add_token,
    del_token,
    list_tokens,
    mask_token,
    merge_config,
    persist_cfg,
    set_app_creds,
)
from bot.env_config import load_config
from bot.poster import caption_from_album_meta, find_cover
from bot.progress import info_card, progress_message
from bot.qobuz_info import fetch_info
from bot.qobuz_worker import cleanup, meta_from_folder, run_download

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
log = logging.getLogger("qobuz-tg")

PLAIN_RE = re.compile(
    r"^(?P<kind>al|ar|tr)[-_]?id\s+(?P<id>[A-Za-z0-9]+)\s*$",
    re.I,
)
STOP_RE = re.compile(r"^/stop_([a-f0-9]{6,12})$", re.I)
AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".wav", ".ogg"}
UPLOAD_LIMIT = 2 * 1024 * 1024 * 1024
UPLOAD_PAUSE = 1.5

# job_id -> {"cancel": bool, "user": int}
JOBS: Dict[str, Dict[str, Any]] = {}

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
    try:
        owners = {int(cfg.OWNER_ID)}
    except (TypeError, ValueError):
        owners = set()
    for x in getattr(cfg, "AUTHORIZED_IDS", []) or []:
        try:
            owners.add(int(x))
        except (TypeError, ValueError):
            pass
    return int(user_id) in owners


def _list_audio(album_dir: Path) -> list[Path]:
    return [
        p
        for p in sorted(album_dir.iterdir())
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    ]


def _audio_meta(path: Path) -> tuple[str, str]:
    title = path.stem
    performer = ""
    try:
        if path.suffix.lower() == ".flac":
            from mutagen.flac import FLAC

            audio = FLAC(path)
            if audio.get("title"):
                title = str(audio["title"][0])
            if audio.get("artist"):
                performer = str(audio["artist"][0])
        elif path.suffix.lower() == ".mp3":
            from mutagen.mp3 import MP3

            audio = MP3(path)
            if audio.tags:
                if audio.tags.get("TIT2"):
                    title = str(audio.tags["TIT2"].text[0])
                if audio.tags.get("TPE1"):
                    performer = str(audio.tags["TPE1"].text[0])
    except Exception:
        pass
    return title, performer


async def _send_with_flood(coro_factory):
    while True:
        try:
            return await coro_factory()
        except FloodWait as e:
            wait = int(getattr(e, "value", None) or getattr(e, "x", 30))
            log.warning("FloodWait %ss", wait)
            await asyncio.sleep(wait + 1)


async def _edit(status, text: str, html: bool = True):
    try:
        await status.edit_text(
            text,
            parse_mode=enums.ParseMode.HTML if html else None,
        )
    except Exception:
        pass


async def _send_tracks(client, user_client, chat_id, files, cfg, status, user_id, job_id):
    sent, skipped = 0, 0
    sender = user_client if user_client is not None else client
    total_files = len(files)
    total_bytes = sum(p.stat().st_size for p in files)
    done_bytes = 0
    t0 = time.time()

    for i, path in enumerate(files, 1):
        if JOBS.get(job_id, {}).get("cancel"):
            await _edit(status, f"⏹ Stopped by user\n/job <code>{job_id}</code>")
            break
        size = path.stat().st_size
        if size > UPLOAD_LIMIT:
            skipped += 1
            continue

        elapsed = max(time.time() - t0, 0.001)
        speed = done_bytes / elapsed
        await _edit(
            status,
            progress_message(
                action="Upload",
                name=path.name,
                user_id=user_id,
                processed=done_bytes,
                total=total_bytes or size,
                speed=speed,
                job_id=job_id,
                tool="telegram",
                extra=f"File {i}/{total_files}",
            ),
        )

        title, performer = _audio_meta(path)

        async def do_audio(p=path, t=title, pr=performer):
            return await sender.send_audio(
                chat_id, p, file_name=p.name, title=t, performer=pr or None
            )

        try:
            await _send_with_flood(do_audio)
            sent += 1
            done_bytes += size
            await asyncio.sleep(UPLOAD_PAUSE)
        except Exception as e:
            log.error("send_audio %s: %s", path.name, e)

            async def do_doc(p=path):
                return await sender.send_document(chat_id, p, file_name=p.name)

            try:
                await _send_with_flood(do_doc)
                sent += 1
                done_bytes += size
                await asyncio.sleep(UPLOAD_PAUSE)
            except Exception as e2:
                log.error("Upload failed %s: %s", path.name, e2)
                skipped += 1

    return sent, skipped


async def _run_job(client, message, kind, id_, cfg, user_client):
    if not message.from_user or not _allowed(message.from_user.id, cfg):
        uid = message.from_user.id if message.from_user else "?"
        await message.reply_text(
            f"Unauthorized.\nYour id: `{uid}`\nSet OWNER_ID or AUTHORIZED_IDS to this."
        )
        return

    user_id = message.from_user.id
    job_id = uuid.uuid4().hex[:8]
    JOBS[job_id] = {"cancel": False, "user": user_id}

    status = await message.reply_text(
        f"⏳ Fetching {kind} info…\n<code>{id_}</code>\n/stop_{job_id}",
        parse_mode=enums.ParseMode.HTML,
    )

    job_dir = None
    try:
        # ── 1) Info card ──────────────────────────────────────────────
        try:
            info = await asyncio.to_thread(fetch_info, kind, id_, cfg)
            card = info_card(kind, info)
            card += f"\n\n/stop_{job_id}"
            await _edit(status, card)
            await asyncio.sleep(1.2)
        except Exception as e:
            log.warning("info fetch failed: %s", e)
            await _edit(
                status,
                f"⚠️ Could not fetch info ({e})\nContinuing download…\n/stop_{job_id}",
            )

        if JOBS[job_id]["cancel"]:
            await _edit(status, f"⏹ Cancelled before download\n/stop_{job_id}")
            return

        # ── 2) Download ───────────────────────────────────────────────
        await _edit(
            status,
            progress_message(
                action="Download",
                name=f"{kind} {id_}",
                user_id=user_id,
                processed=0,
                total=0,
                speed=0,
                job_id=job_id,
                tool="qobuz",
                extra="Fetching from Qobuz…",
            ),
        )
        job_dir, album_dirs = await asyncio.to_thread(run_download, kind, id_, cfg)

        if JOBS[job_id]["cancel"]:
            await _edit(status, f"⏹ Cancelled after download\n/stop_{job_id}")
            return

        if not album_dirs:
            await _edit(status, "Download finished but no album folder found.")
            return

        # ── 3) Post + upload ──────────────────────────────────────────
        channel = int(cfg.CHANNEL_ID)
        total_sent = total_skip = posted = 0

        for album_dir in album_dirs:
            if JOBS[job_id]["cancel"]:
                break
            meta = meta_from_folder(album_dir)
            caption = caption_from_album_meta(meta)
            cover = find_cover(album_dir)

            await _edit(
                status,
                progress_message(
                    action="Upload",
                    name=str(meta.get("title") or album_dir.name),
                    user_id=user_id,
                    processed=0,
                    total=0,
                    speed=0,
                    job_id=job_id,
                    tool="telegram",
                    extra="Sending poster…",
                ),
            )

            async def send_poster(c=cover, cap=caption):
                if c and c.is_file():
                    return await client.send_photo(
                        channel,
                        c,
                        caption=cap[:1024],
                        parse_mode=enums.ParseMode.HTML,
                    )
                return await client.send_message(
                    channel, cap, parse_mode=enums.ParseMode.HTML
                )

            await _send_with_flood(send_poster)
            posted += 1
            await asyncio.sleep(UPLOAD_PAUSE)

            if getattr(cfg, "SEND_TRACKS", True):
                s, k = await _send_tracks(
                    client,
                    user_client,
                    channel,
                    _list_audio(album_dir),
                    cfg,
                    status,
                    user_id,
                    job_id,
                )
                total_sent += s
                total_skip += k

        done = (
            f"✅ <b>Done</b>\n"
            f"Posters: {posted}\n"
            f"Tracks sent: {total_sent}\n"
            f"Skipped: {total_skip}\n"
            f"Local files deleted.\n"
            f"Job: <code>{job_id}</code>"
        )
        if JOBS.get(job_id, {}).get("cancel"):
            done = f"⏹ <b>Stopped</b>\n" + done
        await _edit(status, done)
    except Exception as exc:
        log.exception("job failed")
        try:
            await _edit(status, f"❌ Error:\n<code>{exc}</code>")
        except Exception:
            await message.reply_text(f"❌ Error:\n{exc}")
    finally:
        JOBS.pop(job_id, None)
        if job_dir and getattr(cfg, "DELETE_AFTER_POST", True):
            cleanup(job_dir)


def main() -> None:
    log.info("Loading config (lib=%s)…", log_lib)
    cfg = _load_config()

    if not str(getattr(cfg, "BOT_TOKEN", "") or "").strip():
        raise SystemExit("BOT_TOKEN missing")
    if not getattr(cfg, "TELEGRAM_API", None):
        raise SystemExit("TELEGRAM_API missing")
    if not str(getattr(cfg, "TELEGRAM_HASH", "") or "").strip():
        raise SystemExit("TELEGRAM_HASH missing")

    api_id = int(cfg.TELEGRAM_API)
    api_hash = str(cfg.TELEGRAM_HASH)
    sessions = Path(getattr(cfg, "TEMP_DIR", "/tmp/qobuz-tg")) / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)

    log.info(
        "OWNER_ID=%s CHANNEL_ID=%s",
        getattr(cfg, "OWNER_ID", None),
        getattr(cfg, "CHANNEL_ID", None),
    )

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
        uid = message.from_user.id if message.from_user else None
        ok = uid is not None and _allowed(uid, cfg)
        text = (
            f"**Qobuz-TG online** ({log_lib})\n"
            f"Your id: `{uid}`\n"
            f"Authorized: **{'yes' if ok else 'no'}**\n\n"
        )
        if ok:
            text += (
                "`/al_id` `/ar_id` `/tr_id`\n"
                "Shows full info, then downloads with progress.\n"
                "Cancel: `/stop_<jobid>`\n\n"
                "`/qobuz` `/qobuz_add` `/qobuz_list` …"
            )
        await message.reply_text(text)

    @app.on_message(filters.regex(STOP_RE))
    async def cmd_stop(_, message: Message):
        if not message.from_user or not _allowed(message.from_user.id, cfg):
            return
        m = STOP_RE.match((message.text or "").strip())
        if not m:
            return
        jid = m.group(1).lower()
        if jid in JOBS:
            JOBS[jid]["cancel"] = True
            await message.reply_text(f"⏹ Stop requested for `{jid}`")
        else:
            await message.reply_text(f"No active job `{jid}`")

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
            f"quality: `{getattr(cfg, 'QUALITY', '')}`"
        )

    @app.on_message(filters.command("qobuz_list"))
    async def cmd_qobuz_list(_, message: Message):
        if not message.from_user or not _allowed(message.from_user.id, cfg):
            return await message.reply_text("Unauthorized.")
        toks = list_tokens(cfg)
        if not toks:
            return await message.reply_text("No tokens.")
        lines = [f"{i}. `{mask_token(t)}`" for i, t in enumerate(toks, 1)]
        await message.reply_text("**Tokens**\n" + "\n".join(lines))

    @app.on_message(filters.command("qobuz_add"))
    async def cmd_qobuz_add(_, message: Message):
        if not message.from_user or not _allowed(message.from_user.id, cfg):
            return await message.reply_text("Unauthorized.")
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            return await message.reply_text("Usage: /qobuz_add <token>")
        n = add_token(cfg, parts[1].strip())
        await message.reply_text(f"✅ Token added. Total: {n}")

    @app.on_message(filters.command("qobuz_del"))
    async def cmd_qobuz_del(_, message: Message):
        if not message.from_user or not _allowed(message.from_user.id, cfg):
            return await message.reply_text("Unauthorized.")
        parts = (message.text or "").split()
        if len(parts) < 2 or not parts[1].isdigit():
            return await message.reply_text("Usage: /qobuz_del <n>")
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
        await message.reply_text("✅ Updated.")

    @app.on_message(filters.command("qobuz_quality"))
    async def cmd_qobuz_quality(_, message: Message):
        if not message.from_user or not _allowed(message.from_user.id, cfg):
            return await message.reply_text("Unauthorized.")
        parts = (message.text or "").split()
        allowed = {"hi-res-192", "hi-res", "cd", "mp3"}
        if len(parts) < 2 or parts[1] not in allowed:
            return await message.reply_text("Usage: /qobuz_quality <hi-res-192|hi-res|cd|mp3>")
        cfg.QUALITY = parts[1]
        persist_cfg(cfg)
        await message.reply_text(f"✅ Quality `{parts[1]}`")

    @app.on_message(filters.command("save_config"))
    async def cmd_save(_, message: Message):
        if not message.from_user or not _allowed(message.from_user.id, cfg):
            return await message.reply_text("Unauthorized.")
        ok = persist_cfg(cfg)
        await message.reply_text("Saved." if ok else "Need DATABASE_URL.")

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

    log.info("Starting client…")

    async def runner():
        await app.start()
        if user_client:
            await user_client.start()
        me = await app.get_me()
        log.info("Bot online @%s (id=%s)", me.username, me.id)
        await idle()
        await app.stop()
        if user_client:
            await user_client.stop()

    app.run(runner())


if __name__ == "__main__":
    main()
