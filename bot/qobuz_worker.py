"""Download via qobuz-dl CLI, with per-album progress for artists."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger("qobuz-tg.worker")

ProgressCb = Optional[Callable[..., None]]
CancelCb = Optional[Callable[[], bool]]


def _write_qobuz_config(cfg: Any, work_dir: Path) -> Path:
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


def _run_cli(prefix: str, id_: str, timeout: int) -> None:
    cmd = ["qobuz-dl", "dl", prefix, str(id_)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    # qobuz-dl sometimes exits non-zero even after tracks save (rich/warnings)
    if proc.returncode == 0:
        return
    if "✓ Done!" in out or "Done!" in out:
        log.warning("qobuz-dl exit %s but Done! seen — treating as OK", proc.returncode)
        return
    err = out.strip() or "qobuz-dl failed"
    raise RuntimeError(err[-1500:])


def _list_artist_album_ids(cfg: Any, artist_id: str) -> List[str]:
    from bot.qobuz_info import _get

    release_types = (
        "album",
        "epSingle",
        "single",
        "live",
        "compilation",
        "various-artist",
        "download",
    )
    seen: set = set()
    ordered: List[str] = []
    for rtype in release_types:
        offset = 0
        for _ in range(30):
            try:
                data = _get(
                    cfg,
                    "artist/getReleasesList",
                    artist_id=artist_id,
                    release_type=rtype,
                    limit=100,
                    offset=offset,
                    sort="release_date",
                    track_size=1000,
                )
            except Exception as e:
                log.debug("releases %s@%s: %s", rtype, offset, e)
                break
            items = data.get("items") or []
            if not items:
                break
            for it in items:
                aid = str(it.get("id") or it.get("qobuz_id") or "")
                if aid and aid not in seen:
                    seen.add(aid)
                    ordered.append(aid)
            if not data.get("has_more") and len(items) < 100:
                break
            offset += 100
    return ordered


def _album_label(cfg: Any, album_id: str) -> str:
    try:
        from bot.qobuz_info import album_info

        info = album_info(cfg, album_id)
        title = info.get("title") or album_id
        artist = info.get("artist") or ""
        return f"{artist} — {title}" if artist else title
    except Exception:
        return str(album_id)


def run_download(
    kind: str,
    id_: str,
    cfg: Any,
    on_progress: ProgressCb = None,
    should_cancel: CancelCb = None,
) -> Tuple[Path, List[Path]]:
    base = Path(getattr(cfg, "TEMP_DIR", "/tmp/qobuz-tg"))
    job_dir = base / f"job-{uuid.uuid4().hex[:10]}"
    job_dir.mkdir(parents=True, exist_ok=True)
    _write_qobuz_config(cfg, job_dir)
    timeout = int(getattr(cfg, "DOWNLOAD_TIMEOUT", 3600))

    if kind == "artist":
        album_ids = _list_artist_album_ids(cfg, str(id_))
        total = len(album_ids)
        if on_progress:
            on_progress(0, total, f"Found {total} releases")
        if not album_ids:
            _run_cli("ar-id", id_, timeout)
            return job_dir, _find_album_dirs(job_dir)

        for i, aid in enumerate(album_ids, 1):
            if should_cancel and should_cancel():
                log.info("artist download cancelled at %s/%s", i, total)
                break
            label = _album_label(cfg, aid)
            if on_progress:
                on_progress(i, total, label)
            try:
                _run_cli("al-id", aid, timeout)
            except Exception as e:
                log.warning("album %s failed: %s", aid, e)
                continue
        return job_dir, _find_album_dirs(job_dir)

    prefix = {"album": "al-id", "track": "tr-id"}[kind]
    if on_progress:
        on_progress(0, 1, f"{kind} {id_}")
    _run_cli(prefix, id_, timeout)
    if on_progress:
        on_progress(1, 1, f"{kind} {id_} done")
    return job_dir, _find_album_dirs(job_dir)


def _find_album_dirs(root: Path) -> List[Path]:
    found: List[Path] = []
    for p in root.rglob("*"):
        if not p.is_dir():
            continue
        has_cover = (p / "cover.jpg").exists()
        has_audio = any(p.glob("*.flac")) or any(p.glob("*.mp3"))
        if has_cover or has_audio:
            found.append(p)
    found.sort(key=lambda d: len(d.parts), reverse=True)
    result: List[Path] = []
    for d in found:
        if any(d in c.parents for c in result):
            continue
        result.append(d)
    return result or ([root] if any(root.rglob("*.flac")) else [])


def meta_from_folder(album_dir: Path) -> Dict[str, Any]:
    name = album_dir.name
    artist = album_dir.parent.name if album_dir.parent != album_dir else ""
    title, year, quality, genre = name, "", "", ""

    if " - " in name and "[" in name:
        left, _, rest = name.partition(" - ")
        title = left.strip()
        year_part, _, qpart = rest.partition("[")
        year = year_part.strip()
        quality = qpart.rstrip("]").strip()

    tracks = len(list(album_dir.glob("*.flac"))) + len(list(album_dir.glob("*.mp3")))

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
