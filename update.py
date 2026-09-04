"""Pull latest code from UPSTREAM_REPO (Aeon-MLTB style).
Run manually: python update.py
Do NOT run automatically on Heroku boot.
"""

from __future__ import annotations

import logging
import os
import subprocess
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


def main() -> None:
    cfg = _cfg()
    repo = cfg["UPSTREAM_REPO"]
    branch = cfg["UPSTREAM_BRANCH"]
    if not repo:
        log.error("UPSTREAM_REPO empty — skip")
        return

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
        log.info("Updated to latest from %s (%s)", repo, branch)
    else:
        log.error("Update failed — continuing with existing files")

    for name, content in backup.items():
        Path(name).write_bytes(content)
        log.info("Restored local %s", name)


if __name__ == "__main__":
    main()
