"""Build Telegram album poster caption (HTML blockquote)."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, Optional


def build_caption(
    title: str,
    artist: str = "",
    year: str = "",
    tracks: int | str = "",
    quality: str = "",
    genre: str = "",
) -> str:
    lines: list[str] = [f"📖 {html.escape(str(title))}"]
    if artist:
        lines.append(f"🎤 Artist: {html.escape(str(artist))}")
    if year:
        lines.append(f"📅 Year: {html.escape(str(year))}")
    if tracks not in ("", None):
        lines.append(f"🎵 Tracks: {html.escape(str(tracks))}")
    if quality:
        lines.append(f"🎧 Quality: {html.escape(str(quality))}")
    if genre:
        lines.append(f"🏷️ Genre: {html.escape(str(genre))}")
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
