"""Download via qobuz-dl CLI, collect album folders, wipe temp."""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _write_qobuz_config(cfg: Any, work_dir: Path) -> Path:
    """Write a one-shot config for qobuz-dl under ~/.config is global;
    we set env by writing the standard config path the CLI uses.
    """
    # qobuz-dl reads ~/.config/qobuz-dl/config.json — write there for the job.
    cfg_dir = Path.home() / ".config" / "qobuz-dl"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    path = cfg_dir / "config.json"

    data = {
        "app_id": str(cfg.QOBUZ_APP_ID),
        "secret": str(cfg.QOBUZ_SECRET),
        "auth_tokens": list(cfg.QOBUZ_AUTH_TOKENS),
        "download_dir": str(work_dir),
        "quality": getattr(cfg, "QUALITY", "hi-res-192"),
        "folder_template": getattr(
            cfg, "FOLDER_TEMPLATE", "{main_artist}/{album} - {year} [{quality}]"
        ),
        "track_template": getattr(cfg, "TRACK_TEMPLATE", "{title}"),
        "quality_fallback": True,
        "quality_fallback_path": ["hi-res-192", "hi-res", "cd"],
        "duration_check": True,
        "save_cover": True,
        "embed_metadata": True,
        "skip_existing": False,
        "retries": 3,
        "multi_disc": True,
        "on_final_failure": "delete_partial",
        "include_version": True,
        "cover_size": "original",
        "embed_cover_size": "large",
        "embed_cover_oversize_action": "use_large",
    }
    path.write_text(json.dumps(data, indent=2))
    return path


def run_download(kind: str, id_: str, cfg: Any) -> Tuple[Path, List[Path]]:
    """Run qobuz-dl for al/ar/tr. Returns (job_dir, album_dirs)."""
    base = Path(getattr(cfg, "TEMP_DIR", "/tmp/qobuz-tg"))
    job_dir = base / f"job-{uuid.uuid4().hex[:10]}"
    job_dir.mkdir(parents=True, exist_ok=True)

    _write_qobuz_config(cfg, job_dir)

    prefix = {"album": "al-id", "artist": "ar-id", "track": "tr-id"}[kind]
    cmd = ["qobuz-dl", "dl", prefix, str(id_)]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=int(getattr(cfg, "DOWNLOAD_TIMEOUT", 3600)),
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "qobuz-dl failed").strip()
        raise RuntimeError(err[-1500:])

    album_dirs = _find_album_dirs(job_dir)
    return job_dir, album_dirs


def _find_album_dirs(root: Path) -> List[Path]:
    """Dirs that contain cover.jpg or audio files."""
    found: List[Path] = []
    for p in root.rglob("*"):
        if not p.is_dir():
            continue
        has_cover = (p / "cover.jpg").exists()
        has_audio = any(p.glob("*.flac")) or any(p.glob("*.mp3"))
        if has_cover or has_audio:
            # skip parent if child is the real album folder
            found.append(p)
    # prefer deepest dirs (actual album folders)
    found.sort(key=lambda d: len(d.parts), reverse=True)
    # unique by keeping dirs that aren't parents of another found dir
    result: List[Path] = []
    for d in found:
        if any(d in c.parents for c in result):
            continue
        result.append(d)
    return result or ([root] if any(root.rglob("*.flac")) else [])


def meta_from_folder(album_dir: Path) -> Dict[str, Any]:
    """Best-effort metadata from folder name + mutagen."""
    name = album_dir.name
    artist = album_dir.parent.name if album_dir.parent != album_dir else ""
    title, year, quality, genre = name, "", "", ""

    # Pattern: "Album - 2013 [FLAC 24bit 88kHz]"
    if " - " in name and "[" in name:
        left, _, rest = name.partition(" - ")
        title = left.strip()
        year_part, _, qpart = rest.partition("[")
        year = year_part.strip()
        quality = qpart.rstrip("]").strip()

    tracks = len(list(album_dir.glob("*.flac"))) + len(list(album_dir.glob("*.mp3")))

    # try first flac for tags
    try:
        from mutagen.flac import FLAC

        for f in album_dir.glob("*.flac"):
            audio = FLAC(f)
            if audio.get("album"):
                title = str(audio["album"][0])
            if audio.get("albumartist"):
                artist = str(audio["albumartist"][0])
            elif audio.get("artist"):
                artist = str(audio["artist"][0])
            if audio.get("date"):
                year = str(audio["date"][0])[:4]
            if audio.get("genre"):
                genre = str(audio["genre"][0])
            break
    except Exception:
        pass

    return {
        "title": title,
        "artist": artist,
        "year": year,
        "tracks": tracks,
        "quality": quality,
        "genre": genre,
        "path": str(album_dir),
    }


def cleanup(job_dir: Path) -> None:
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
