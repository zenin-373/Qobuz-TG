"""Aeon/MLTB-style status & progress messages (plain text)."""

from __future__ import annotations

import re
import shutil
import time
from typing import Optional

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore


def _bar(pct: float, width: int = 10) -> str:
    pct = max(0.0, min(100.0, float(pct)))
    filled = int(round(width * pct / 100.0))
    return "●" * filled + "○" * (width - filled)


def human_bytes(n: float) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.2f}{unit}" if unit != "B" else f"{int(n)}B"
        n /= 1024.0
    return f"{n:.2f}PB"


def human_speed(bps: float) -> str:
    return f"{human_bytes(bps)}/s"


def human_eta(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0 or seconds == float("inf"):
        return "-"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def system_footer() -> str:
    cpu = ram = free = up = "-"
    try:
        if psutil:
            cpu = f"{psutil.cpu_percent(interval=None):.1f}%"
            vm = psutil.virtual_memory()
            ram = f"{vm.percent:.1f}%"
            up_sec = int(time.time() - psutil.boot_time())
        else:
            up_sec = 0
        disk = shutil.disk_usage("/")
        free = human_bytes(disk.free)
        if up_sec:
            h, rem = divmod(up_sec, 3600)
            m, _ = divmod(rem, 60)
            up = f"{h}h {m}m" if h else f"{m} minutes"
    except Exception:
        pass
    return f"CPU: {cpu} | FREE: {free}\nRAM: {ram} | UPTIME: {up}"


def _plain(s: object) -> str:
    """Strip any HTML-like tags from metadata/filenames."""
    t = str(s or "")
    t = re.sub(r"<[^>]*>", "", t)
    return t.replace("\n", " ").strip()


def progress_message(
    *,
    action: str,
    name: str,
    user_id: int | str,
    processed: int = 0,
    total: int = 0,
    speed: float = 0.0,
    job_id: str = "",
    tool: str = "telegram",
    extra: str = "",
) -> str:
    if total > 0:
        pct = processed * 100.0 / total
        eta = (total - processed) / speed if speed > 0 else None
    else:
        pct = 0.0
        eta = None

    lines = [
        f"{action}: {_plain(name)}",
        f"by: {user_id}",
        f"{_bar(pct)} {pct:.1f}%",
        f"Processed: {human_bytes(processed)}",
        f"Size: {human_bytes(total) if total else '-'}",
        f"Speed: {human_speed(speed) if speed else '0B/s'}",
        f"Estimated: {human_eta(eta)}",
        f"Tool: {tool}",
    ]
    if job_id:
        lines.append(f"/stop_{job_id}")
    if extra:
        lines.append(_plain(extra))
    lines.append("")
    lines.append(system_footer())
    return "\n".join(lines)


def info_card(kind: str, data: dict) -> str:
    """Pre-download info panel (plain text)."""
    if kind == "album":
        lines = [
            "📀 Album info",
            f"📖 {_plain(data.get('title', ''))}",
            f"🎤 Artist: {_plain(data.get('artist', ''))}",
            f"📅 Year: {_plain(data.get('year', ''))}",
            f"🎵 Tracks: {data.get('tracks', '?')}",
            f"🎧 Quality: {_plain(data.get('quality', ''))}",
            f"🏷️ Genre: {_plain(data.get('genre', ''))}",
            f"⏱ Duration: {_plain(data.get('duration', ''))}",
            f"🆔 { _plain(data.get('id', '')) }",
        ]
    elif kind == "track":
        lines = [
            "🎵 Track info",
            f"📖 {_plain(data.get('title', ''))}",
            f"🎤 Artist: {_plain(data.get('artist', ''))}",
            f"💿 Album: {_plain(data.get('album', ''))}",
            f"📅 Year: {_plain(data.get('year', ''))}",
            f"🎧 Quality: {_plain(data.get('quality', ''))}",
            f"⏱ Duration: {_plain(data.get('duration', ''))}",
            f"🆔 {_plain(data.get('id', ''))}",
        ]
    else:
        lines = [
            "🎤 Artist info",
            f"👤 {_plain(data.get('name', ''))}",
            f"📀 Albums / releases: {data.get('albums', '?')}",
            f"🎵 Tracks (approx): {data.get('tracks', '?')}",
            f"🆔 {_plain(data.get('id', ''))}",
        ]
    return "\n".join(lines)
