"""Build Telegram album poster caption + safe cover prep."""

from __future__ import annotations

import html
import io
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger("qobuz-tg.poster")

# Telegram photo limits (practical)
MAX_PHOTO_BYTES = 9 * 1024 * 1024  # keep under 10MB
MAX_SIDE = 2560


def _clean(s: str) -> str:
    s = str(s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return html.escape(s, quote=True)


def build_caption(
    title: str,
    artist: str = "",
    year: str = "",
    tracks: int | str = "",
    quality: str = "",
    genre: str = "",
) -> str:
    lines: list[str] = [f"📖 {_clean(title)}"]
    if artist:
        lines.append(f"🎤 Artist: {_clean(artist)}")
    if year:
        lines.append(f"📅 Year: {_clean(year)}")
    if tracks not in ("", None):
        lines.append(f"🎵 Tracks: {_clean(tracks)}")
    if quality:
        lines.append(f"🎧 Quality: {_clean(quality)}")
    if genre:
        lines.append(f"🏷️ Genre: {_clean(genre)}")
    body = "\n".join(lines)
    return f"<blockquote>{body}</blockquote>"


def caption_from_album_meta(meta: Dict[str, Any]) -> str:
    return build_caption(
        title=str(meta.get("title") or "Unknown"),
        artist=str(meta.get("artist") or ""),
        year=str(meta.get("year") or ""),
        tracks=meta.get("tracks") or "",
        quality=str(meta.get("quality") or ""),
        genre=str(meta.get("genre") or ""),
    )


def find_cover(album_dir: Path) -> Optional[Path]:
    for name in ("cover.jpg", "cover.jpeg", "folder.jpg", "Cover.jpg", "cover.png"):
        p = album_dir / name
        if p.is_file() and p.stat().st_size > 100:
            return p
    for pat in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
        for p in album_dir.glob(pat):
            if p.is_file() and p.stat().st_size > 100:
                return p
    return None


def prepare_cover_jpeg(src: Path, dest_dir: Optional[Path] = None) -> Optional[Path]:
    """Return a path to a Telegram-safe JPEG, or None if unusable.

    Re-encodes via Pillow when available; otherwise checks JPEG magic bytes.
    """
    if not src or not src.is_file() or src.stat().st_size < 100:
        return None

    out_dir = dest_dir or src.parent
    out = out_dir / "_tg_cover.jpg"

    # Try Pillow re-encode (handles WEBP/PNG/corrupt progressive JPEG)
    try:
        from PIL import Image

        with Image.open(src) as im:
            im = im.convert("RGB")
            w, h = im.size
            if max(w, h) > MAX_SIDE:
                im.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            quality = 90
            im.save(buf, format="JPEG", quality=quality, optimize=True)
            data = buf.getvalue()
            while len(data) > MAX_PHOTO_BYTES and quality > 40:
                quality -= 10
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=quality, optimize=True)
                data = buf.getvalue()
            if len(data) < 100 or len(data) > MAX_PHOTO_BYTES:
                log.warning("Cover still invalid after re-encode (%s bytes)", len(data))
                return None
            out.write_bytes(data)
            return out
    except Exception as e:
        log.warning("Pillow re-encode failed (%s) — trying raw JPEG check", e)

    # Fallback: accept only if already looks like JPEG
    try:
        head = src.read_bytes()[:3]
        if head == b"\xff\xd8\xff" and src.stat().st_size <= MAX_PHOTO_BYTES:
            if src.suffix.lower() in {".jpg", ".jpeg"}:
                return src
            out.write_bytes(src.read_bytes())
            return out
    except Exception:
        pass
    return None
