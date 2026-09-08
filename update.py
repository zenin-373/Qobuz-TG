"""Pull latest code from UPSTREAM_REPO on dyno start (Aeon-MLTB style).

On Heroku there is often no `git` binary — fall back to downloading the
branch zip from GitHub so updates still work.

Procfile:  python update.py; python -m bot
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("update")

# Never overwrite secrets / runtime state
PRESERVE = {"config.py", ".env", "log.txt", "update.py"}
SKIP_PREFIXES = (".git/", "sessions/", "__pycache__/")


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


def _has_git() -> bool:
    return shutil.which("git") is not None


def _github_zip_url(repo: str, branch: str) -> str:
    """https://github.com/owner/repo → archive zip URL."""
    repo = repo.rstrip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]
    # already a github URL
    if "github.com" in repo:
        path = urlparse(repo).path.strip("/")  # owner/repo
        return f"https://github.com/{path}/archive/refs/heads/{branch}.zip"
    return f"https://github.com/{repo}/archive/refs/heads/{branch}.zip"


def _update_via_git(repo: str, branch: str) -> bool:
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
    r = subprocess.run(cmd, shell=True, timeout=120)
    return r.returncode == 0


def _update_via_zip(repo: str, branch: str) -> bool:
    url = _github_zip_url(repo, branch)
    log.info("Downloading %s", url)
    req = Request(url, headers={"User-Agent": "qobuz-tg-update"})
    with urlopen(req, timeout=60) as resp:
        data = resp.read()

    root = Path(".").resolve()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        # GitHub zip top folder: Repo-branch/
        names = zf.namelist()
        if not names:
            return False
        top = names[0].split("/")[0] + "/"

        for info in zf.infolist():
            if info.is_dir():
                continue
            rel = info.filename
            if not rel.startswith(top):
                continue
            rel = rel[len(top) :]
            if not rel or rel in PRESERVE:
                continue
            if any(rel.startswith(p) for p in SKIP_PREFIXES):
                continue
            # only update project files
            if not (
                rel.startswith("bot/")
                or rel in {
                    "Procfile",
                    "requirements.txt",
                    "runtime.txt",
                    "heroku.yml",
                    "update.py",
                    "config_sample.py",
                    "README.md",
                }
                or rel.startswith(".github/")
            ):
                # still allow any .py at root
                if not rel.endswith(".py") and "/" not in rel.rstrip("/"):
                    continue

            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                dst.write(src.read())
    return True


def main() -> None:
    cfg = _cfg()
    repo = (cfg.get("UPSTREAM_REPO") or "").strip()
    branch = (cfg.get("UPSTREAM_BRANCH") or "main").strip()
    if not repo:
        log.warning("UPSTREAM_REPO empty — skip update")
        return

    # Backup secrets
    backup: dict[str, bytes] = {}
    for name in PRESERVE:
        p = Path(name)
        if p.is_file():
            backup[name] = p.read_bytes()

    ok = False
    try:
        if _has_git():
            log.info("git found — updating via git")
            ok = _update_via_git(repo, branch)
        if not ok:
            log.info("Updating via GitHub zip (no git or git failed)")
            ok = _update_via_zip(repo, branch)
        if ok:
            log.info("Updated to latest from %s (%s)", repo, branch)
        else:
            log.error("Update failed — bot will use slug files")
    except Exception as e:
        log.error("Update error: %s — bot will use slug files", e)

    for name, content in backup.items():
        Path(name).write_bytes(content)
        log.info("Restored local %s", name)


if __name__ == "__main__":
    main()
