"""Pull latest code from UPSTREAM_REPO (Aeon-MLTB style)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)
log = logging.getLogger("update")


def _cfg() -> dict:
    data = {}
    try:
        import config as settings  # type: ignore

        for k, v in vars(settings).items():
            if k.isupper():
                data[k] = v.strip() if isinstance(v, str) else v
    except Exception:
        log.info("config.py missing — using environment variables")

    def env(key: str, default=""):
        return data.get(key) or os.getenv(key, default)

    return {
        "BOT_TOKEN": env("BOT_TOKEN"),
        "DATABASE_URL": env("DATABASE_URL", ""),
        "UPSTREAM_REPO": env("UPSTREAM_REPO", "https://github.com/zenin-373/Qobuz-TG"),
        "UPSTREAM_BRANCH": env("UPSTREAM_BRANCH", "main"),
    }


def _maybe_load_upstream_from_mongo(cfg: dict) -> dict:
    url = cfg.get("DATABASE_URL") or ""
    token = cfg.get("BOT_TOKEN") or ""
    if not url or not token:
        return cfg
    try:
        from pymongo import MongoClient

        bot_id = token.split(":", 1)[0]
        client = MongoClient(url, serverSelectionTimeoutMS=8000)
        db = client.qobuz_tg
        doc = db.settings.config.find_one({"_id": bot_id})
        if doc:
            cfg["UPSTREAM_REPO"] = doc.get("UPSTREAM_REPO", cfg["UPSTREAM_REPO"])
            cfg["UPSTREAM_BRANCH"] = doc.get("UPSTREAM_BRANCH", cfg["UPSTREAM_BRANCH"])
            log.info("Loaded UPSTREAM_* from MongoDB")
        client.close()
    except Exception as e:
        log.error("MongoDB error: %s", e)
    return cfg


def main() -> None:
    cfg = _maybe_load_upstream_from_mongo(_cfg())
    repo = cfg["UPSTREAM_REPO"]
    branch = cfg["UPSTREAM_BRANCH"]
    if not repo:
        log.error("UPSTREAM_REPO empty — skip update")
        return

    # Keep local config.py / secrets
    preserve = ["config.py", ".env", "log.txt"]
    backup: dict[str, bytes] = {}
    for name in preserve:
        p = Path(name)
        if p.is_file():
            backup[name] = p.read_bytes()

    if Path(".git").exists():
        subprocess.run(["rm", "-rf", ".git"], check=False)

    cmd = (
        f"git init -q && "
        f'git config user.email "qobuz-tg@local" && '
        f'git config user.name "qobuz-tg" && '
        f"git remote add origin {repo} && "
        f"git fetch origin -q && "
        f"git checkout -f -B {branch} origin/{branch} -q"
    )
    result = subprocess.run(cmd, shell=True)
    if result.returncode == 0:
        log.info("Updated to latest commit from %s (%s)", repo, branch)
    else:
        log.error("Update failed — check UPSTREAM_REPO / branch")
        sys.exit(1)

    for name, content in backup.items():
        Path(name).write_bytes(content)
        log.info("Restored local %s", name)


if __name__ == "__main__":
    main()
