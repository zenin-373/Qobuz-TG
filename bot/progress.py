"""Aeon/MLTB-style status & progress messages (plain text)."""

from __future__ import annotations

import os
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
            # process uptime is more useful than host boot on Heroku
            try:
                p = psutil.Process()
                up_sec = int(time.time() - p.create_time())
            except Exception:
                up_sec = int(time.time() - psutil.boot_time())
        else:
            up_sec = 0

        # Heroku: "/" can report 0; prefer writable work dirs
        free_bytes = 0
        for path in (
            os.environ.get("TEMP_DIR"),
            "/tmp",
            "/app",
            ".",
            "/",
        ):
            if not path:
                continue
            try:
                du = shutil.disk_usage(path)
                if du.free > free_bytes:
                    free_bytes = du.free
            except Exception:
                continue
        free = human_bytes(free_bytes) if free_bytes else "-"

        if up_sec:
            h, rem = divmod(up_sec, 3600)
            m, _ = divmod(rem, 60)
            up = f"{h}h {m}m" if h else f"{m} minutes"
    except Exception:
        pass
    return f"CPU: {cpu} | FREE: {free}\nRAM: {ram} | UPTIME: {up}"


def _plain(s: object) -> str:
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
    indeterminate = total <= 0
    if not indeterminate:
        pct = processed * 100.0 / total
        eta = (total - processed) / speed if speed > 0 else None
        bar = f"{_bar(pct)} {pct:.1f}%"
        size_line = f"Size: {human_bytes(total)}"
        speed_line = f"Speed: {human_speed(speed) if speed else '0B/s'}"
        eta_line = f"Estimated: {human_eta(eta)}"
        proc_line = f"Processed: {human_bytes(processed)}"
    else:
        # Download via qobuz-dl has no byte progress — don't show fake 0%
        bar = "⏳ working…"
        size_line = "Size: (unknown until upload)"
        speed_line = "Speed: -"
        eta_line = "Estimated: -"
        proc_line = "Processed: -"

    lines = [
        f"{action}: {_plain(name)}",
        f"by: {user_id}",
        bar,
        proc_line,
        size_line,
        speed_line,
        eta_line,
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
            f"🆔 {_plain(data.get('id', ''))}",
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
