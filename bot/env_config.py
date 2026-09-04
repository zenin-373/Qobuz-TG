"""Build a config object from environment variables (Heroku Config Vars)."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import Any


def _bool(val: str | None, default: bool = False) -> bool:
    if val is None or val == "":
        return default
    return val.strip().lower() in {"1", "true", "yes", "on", "y"}


def _int(val: str | None, default: int = 0) -> int:
    try:
        return int(val) if val not in (None, "") else default
    except ValueError:
        return default


def _list(val: str | None) -> list:
    if not val:
        return []
    val = val.strip()
    if val.startswith("["):
        try:
            return list(json.loads(val))
        except Exception:
            pass
    return [x.strip() for x in val.split(",") if x.strip()]


def from_environ() -> SimpleNamespace:
    tokens = _list(os.getenv("QOBUZ_AUTH_TOKENS"))
    return SimpleNamespace(
        BOT_TOKEN=os.getenv("BOT_TOKEN", ""),
        OWNER_ID=_int(os.getenv("OWNER_ID")),
        CHANNEL_ID=_int(os.getenv("CHANNEL_ID")),
        TELEGRAM_API=_int(os.getenv("TELEGRAM_API")),
        TELEGRAM_HASH=os.getenv("TELEGRAM_HASH", ""),
        USER_SESSION_STRING=os.getenv("USER_SESSION_STRING", ""),
        AUTHORIZED_IDS=_list(os.getenv("AUTHORIZED_IDS")),
        DATABASE_URL=os.getenv("DATABASE_URL", ""),
        UPSTREAM_REPO=os.getenv("UPSTREAM_REPO", "https://github.com/zenin-373/Qobuz-TG"),
        UPSTREAM_BRANCH=os.getenv("UPSTREAM_BRANCH", "main"),
        QOBUZ_APP_ID=os.getenv("QOBUZ_APP_ID", ""),
        QOBUZ_SECRET=os.getenv("QOBUZ_SECRET", ""),
        QOBUZ_AUTH_TOKENS=tokens,
        TEMP_DIR=os.getenv("TEMP_DIR", "/tmp/qobuz-tg"),
        QUALITY=os.getenv("QUALITY", "hi-res-192"),
        FOLDER_TEMPLATE=os.getenv(
            "FOLDER_TEMPLATE", "{main_artist}/{album} - {year} [{quality}]"
        ),
        TRACK_TEMPLATE=os.getenv("TRACK_TEMPLATE", "{title}"),
        DOWNLOAD_TIMEOUT=_int(os.getenv("DOWNLOAD_TIMEOUT"), 7200),
        DELETE_AFTER_POST=_bool(os.getenv("DELETE_AFTER_POST"), True),
        SEND_TRACKS=_bool(os.getenv("SEND_TRACKS"), True),
        MAX_TG_FILE_MB=_int(os.getenv("MAX_TG_FILE_MB"), 49),
    )


def load_config() -> Any:
    """Prefer config.py; fall back to environment (Heroku)."""
    try:
        import config as cfg  # type: ignore

        return cfg
    except ImportError:
        env = from_environ()
        if not env.BOT_TOKEN:
            raise SystemExit(
                "No config.py and no BOT_TOKEN env var. "
                "Copy config_sample.py or set Heroku Config Vars."
            )
        return env
