"""Build Telegram album poster caption."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


def build_caption(
    title: str,
    artist: str,
    year: str = "",
    tracks: int | str = "",
    quality: str = "",
    genre: str = "",
) -> str:
    lines = [f"📖 {title}"]
    if artist:
        lines.append(f"🎤 Artist: {artist}")
    if year:
        lines.append(f"📅 Year: {year}")
    if tracks not in ("", None):
        lines.append(f"🎵 Tracks: {tracks}")
    if quality:
        lines.append(f"🎧 Quality: {quality}")
    if genre:
        lines.append(f"🏷️ Genre: {genre}")
    return "\n".join(lines)


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
