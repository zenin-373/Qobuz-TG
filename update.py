"""Pull latest code from UPSTREAM_REPO on dyno start (Aeon-MLTB style).

Procfile runs:  python update.py; python -m bot
If git pull fails, the bot still starts with the last slug files.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    stream=sys.stdout,
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
        pass

    def env(key: str, default=""):
        return data.get(key) or os.getenv(key, default)

    return {
        "UPSTREAM_REPO": env(
            "UPSTREAM_REPO", "https://github.com/zenin-373/Qobuz-TG"
        ),
        "UPSTREAM_BRANCH": env("UPSTREAM_BRANCH", "main"),
    }


def main() -> None:
    cfg = _cfg()
    repo = (cfg.get("UPSTREAM_REPO") or "").strip()
    branch = (cfg.get("UPSTREAM_BRANCH") or "main").strip()
    if not repo:
        log.warning("UPSTREAM_REPO empty — skip update")
        return

    # Keep local secrets if present on disk
    preserve = ["config.py", ".env", "log.txt"]
    backup: dict[str, bytes] = {}
    for name in preserve:
        p = Path(name)
        if p.is_file():
            backup[name] = p.read_bytes()

    try:
        if Path(".git").exists():
            subprocess.run(["rm", "-rf", ".git"], check=False)

        cmd = (
            "git init -q && "
            'git config user.email "qobuz-tg@local" && '
            'git config user.name "qobuz-tg" && '
            f"git remote add origin {repo} && "
            f"git fetch --depth=1 origin {branch} -q && "
            f"git checkout -f -B {branch} FETCH_HEAD -q"
        )
        result = subprocess.run(cmd, shell=True, timeout=120)
        if result.returncode == 0:
            log.info("Updated to latest commit from %s (%s)", repo, branch)
        else:
            log.error("git update failed (code %s) — bot will use slug files", result.returncode)
    except Exception as e:
        log.error("Update error: %s — bot will use slug files", e)

    for name, content in backup.items():
        Path(name).write_bytes(content)
        log.info("Restored local %s", name)


if __name__ == "__main__":
    main()
