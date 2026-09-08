"""Fetch Qobuz metadata for pre-download info cards."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict

import requests

API = "https://www.qobuz.com/api.json/0.2"


def _headers(cfg) -> dict:
    tokens = list(getattr(cfg, "QOBUZ_AUTH_TOKENS", []) or [])
    token = tokens[0] if tokens else ""
    return {
        "X-App-Id": str(getattr(cfg, "QOBUZ_APP_ID", "")),
        "X-User-Auth-Token": token,
        "User-Agent": "qobuz-tg/1.0",
    }


def _get(cfg, endpoint: str, **params) -> dict:
    r = requests.get(
        f"{API}/{endpoint.lstrip('/')}",
        headers=_headers(cfg),
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _fmt_duration(sec) -> str:
    try:
        sec = int(sec or 0)
    except (TypeError, ValueError):
        return ""
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"


def _quality_label(item: dict) -> str:
    mqa = item.get("maximum_sampling_rate") or item.get("hires_streamable")
    bit = item.get("maximum_bit_depth")
    sr = item.get("maximum_sampling_rate")
    if bit and sr:
        return f"{bit}-bit / {sr}kHz"
    if item.get("streamable"):
        return "streamable"
    return ""


def album_info(cfg, album_id: str) -> Dict[str, Any]:
    data = _get(cfg, "album/get", album_id=album_id, extra="track_ids")
    tracks = data.get("tracks", {}).get("items") or []
    if isinstance(tracks, dict):
        tracks = tracks.get("items") or []
    artist = (data.get("artist") or {}).get("name") or ""
    if not artist and data.get("artists"):
        artist = ", ".join(
            a.get("name", "") for a in data["artists"] if a.get("name")
        )
    return {
        "id": str(data.get("id") or album_id),
        "title": data.get("title") or "",
        "artist": artist,
        "year": str((data.get("release_date_original") or "")[:4]),
        "tracks": len(tracks) or data.get("tracks_count") or "?",
        "quality": _quality_label(data),
        "genre": (data.get("genre") or {}).get("name") or "",
        "duration": _fmt_duration(data.get("duration")),
    }


def track_info(cfg, track_id: str) -> Dict[str, Any]:
    data = _get(cfg, "track/get", track_id=track_id)
    album = data.get("album") or {}
    artist = (data.get("performer") or {}).get("name") or (
        (album.get("artist") or {}).get("name") or ""
    )
    return {
        "id": str(data.get("id") or track_id),
        "title": data.get("title") or "",
        "artist": artist,
        "album": album.get("title") or "",
        "year": str((album.get("release_date_original") or "")[:4]),
        "quality": _quality_label(data) or _quality_label(album),
        "duration": _fmt_duration(data.get("duration")),
    }


def artist_info(cfg, artist_id: str) -> Dict[str, Any]:
    """Count releases across types + approximate track count."""
    name = ""
    try:
        page = _get(cfg, "artist/page", artist_id=artist_id, sort="release_date")
        name = (page.get("name") or page.get("artist", {}).get("name") or "")
    except Exception:
        page = {}

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
    track_est = 0
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
            except Exception:
                break
            items = data.get("items") or []
            if not items:
                break
            for it in items:
                aid = str(it.get("id") or it.get("qobuz_id") or "")
                if aid and aid not in seen:
                    seen.add(aid)
                    track_est += int(it.get("tracks_count") or 0)
            if not data.get("has_more") and len(items) < 100:
                break
            offset += 100

    if not name:
        name = f"Artist {artist_id}"
    return {
        "id": str(artist_id),
        "name": name,
        "albums": len(seen),
        "tracks": track_est or "?",
    }


def fetch_info(kind: str, id_: str, cfg) -> Dict[str, Any]:
    if kind == "album":
        return album_info(cfg, id_)
    if kind == "track":
        return track_info(cfg, id_)
    return artist_info(cfg, id_)
