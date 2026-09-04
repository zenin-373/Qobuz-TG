"""Load / save bot settings from MongoDB (DATABASE_URL)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

log = logging.getLogger("qobuz-tg.db")

STORED_KEYS = (
    "BOT_TOKEN",
    "OWNER_ID",
    "CHANNEL_ID",
    "AUTHORIZED_IDS",
    "TELEGRAM_API",
    "TELEGRAM_HASH",
    "USER_SESSION_STRING",
    "QOBUZ_APP_ID",
    "QOBUZ_SECRET",
    "QOBUZ_AUTH_TOKENS",
    "TEMP_DIR",
    "QUALITY",
    "FOLDER_TEMPLATE",
    "TRACK_TEMPLATE",
    "DELETE_AFTER_POST",
    "SEND_TRACKS",
    "MAX_TG_FILE_MB",
    "UPSTREAM_REPO",
    "UPSTREAM_BRANCH",
)


def _bot_id(token: str) -> str:
    return token.split(":", 1)[0]


def load_from_mongo(database_url: str, bot_token: str) -> Dict[str, Any]:
    if not database_url or not bot_token:
        return {}
    try:
        from pymongo import MongoClient

        client = MongoClient(database_url, serverSelectionTimeoutMS=10000)
        db = client.qobuz_tg
        doc = db.settings.config.find_one({"_id": _bot_id(bot_token)})
        client.close()
        if not doc:
            return {}
        out = {k: doc[k] for k in STORED_KEYS if k in doc}
        log.info("Loaded %d keys from MongoDB", len(out))
        return out
    except Exception as e:
        log.error("MongoDB load failed: %s", e)
        return {}


def save_to_mongo(database_url: str, bot_token: str, data: Dict[str, Any]) -> bool:
    if not database_url or not bot_token:
        return False
    try:
        from pymongo import MongoClient

        payload = {k: data[k] for k in STORED_KEYS if k in data}
        payload["_id"] = _bot_id(bot_token)
        client = MongoClient(database_url, serverSelectionTimeoutMS=10000)
        db = client.qobuz_tg
        db.settings.config.replace_one({"_id": payload["_id"]}, payload, upsert=True)
        client.close()
        log.info("Saved config to MongoDB")
        return True
    except Exception as e:
        log.error("MongoDB save failed: %s", e)
        return False


def merge_config(module_cfg: Any, database_url: str = "") -> Any:
    token = getattr(module_cfg, "BOT_TOKEN", "") or ""
    url = database_url or getattr(module_cfg, "DATABASE_URL", "") or ""
    overrides = load_from_mongo(url, token)
    for k, v in overrides.items():
        setattr(module_cfg, k, v)
    return module_cfg


def cfg_snapshot(cfg: Any) -> Dict[str, Any]:
    return {k: getattr(cfg, k) for k in dir(cfg) if k.isupper()}


def persist_cfg(cfg: Any) -> bool:
    """Write full config snapshot to Mongo if DATABASE_URL is set."""
    url = getattr(cfg, "DATABASE_URL", "") or ""
    token = getattr(cfg, "BOT_TOKEN", "") or ""
    if not url:
        return False
    return save_to_mongo(url, token, cfg_snapshot(cfg))


def mask_token(t: str) -> str:
    t = t.strip()
    if len(t) <= 10:
        return "***"
    return t[:6] + "…" + t[-4:]


def list_tokens(cfg: Any) -> List[str]:
    toks = list(getattr(cfg, "QOBUZ_AUTH_TOKENS", []) or [])
    return [str(x) for x in toks if str(x).strip()]


def add_token(cfg: Any, token: str) -> int:
    token = token.strip()
    toks = list_tokens(cfg)
    if token not in toks:
        toks.append(token)
    cfg.QOBUZ_AUTH_TOKENS = toks
    persist_cfg(cfg)
    return len(toks)


def del_token(cfg: Any, index: int) -> bool:
    toks = list_tokens(cfg)
    if index < 1 or index > len(toks):
        return False
    toks.pop(index - 1)
    cfg.QOBUZ_AUTH_TOKENS = toks
    persist_cfg(cfg)
    return True


def set_app_creds(cfg: Any, app_id: str, secret: str) -> None:
    cfg.QOBUZ_APP_ID = app_id.strip()
    cfg.QOBUZ_SECRET = secret.strip()
    persist_cfg(cfg)
