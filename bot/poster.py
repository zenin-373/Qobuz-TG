"""Build Telegram album poster caption (HTML blockquote)."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any, Dict, Optional


def _clean(s: str) -> str:
    """Escape HTML and strip any residual tags from metadata."""
    s = str(s or "")
    s = re.sub(r"<[^>]+>", "", s)  # drop raw tags from Qobuz metadata
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
    for name in ("cover.jpg", "cover.jpeg", "folder.jpg", "Cover.jpg"):
        p = album_dir / name
        if p.is_file():
            return p
    for p in album_dir.glob("*.jpg"):
        return p
    return None
