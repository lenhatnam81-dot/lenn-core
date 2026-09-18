"""Trích xuất metadata & thông số kỹ thuật bằng ffprobe.

Ghi chú kỹ thuật: bản MVP này dùng `ffprobe` (đi kèm ffmpeg, đã có sẵn trên
máy chủ) thay vì thư viện mutagen, vì môi trường build hiện tại không tải
được gói pip mới (chính sách mạng chặn pypi.org). ffprobe đọc được tag của
hầu hết định dạng audiophile quan tâm: FLAC, ALAC, WAV/AIFF, DSF/DFF (DSD),
MP3, AAC/M4A, OGG/Opus, APE, WavPack — nên đây là lựa chọn thay thế hợp lệ,
không phải giải pháp tạm bợ kém tin cậy.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TrackMetadata:
    title: str | None
    artist: str | None
    album: str | None
    album_artist: str | None
    track_no: int | None
    disc_no: int | None
    year: int | None
    genre: str | None
    duration_seconds: float | None
    codec: str | None
    sample_rate: int | None
    bit_depth: int | None
    channels: int | None
    bitrate: int | None


def _first_int(*values) -> int | None:
    for v in values:
        if v is None:
            continue
        try:
            # "3/12" (track/total) -> lấy phần trước dấu '/'
            s = str(v).split("/")[0].strip()
            if s:
                return int(float(s))
        except (ValueError, TypeError):
            continue
    return None


def probe_file(path: Path) -> TrackMetadata | None:
    """Chạy ffprobe trên 1 file, trả về TrackMetadata hoặc None nếu lỗi/không
    phải file audio hợp lệ."""
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                str(path),
            ],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None

    fmt = data.get("format", {}) or {}
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}

    audio_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "audio":
            audio_stream = stream
            break
    if audio_stream is None:
        return None
    stream_tags = {k.lower(): v for k, v in (audio_stream.get("tags") or {}).items()}
    # tag ở mức track (stream) được ưu tiên hơn tag ở mức container (format)
    merged_tags = {**tags, **stream_tags}

    duration = None
    for src in (audio_stream.get("duration"), fmt.get("duration")):
        if src is not None:
            try:
                duration = float(src)
                break
            except (ValueError, TypeError):
                pass

    bit_depth = audio_stream.get("bits_per_raw_sample") or audio_stream.get("bits_per_sample")
    try:
        bit_depth = int(bit_depth) if bit_depth else None
    except (ValueError, TypeError):
        bit_depth = None

    year = None
    date_val = merged_tags.get("date") or merged_tags.get("year")
    if date_val:
        year = _first_int(str(date_val)[:4])

    return TrackMetadata(
        title=merged_tags.get("title"),
        artist=merged_tags.get("artist"),
        album=merged_tags.get("album"),
        album_artist=merged_tags.get("album_artist") or merged_tags.get("albumartist") or merged_tags.get("artist"),
        track_no=_first_int(merged_tags.get("track")),
        disc_no=_first_int(merged_tags.get("disc")),
        year=year,
        genre=merged_tags.get("genre"),
        duration_seconds=duration,
        codec=audio_stream.get("codec_name"),
        sample_rate=_first_int(audio_stream.get("sample_rate")),
        bit_depth=bit_depth,
        channels=_first_int(audio_stream.get("channels")),
        bitrate=_first_int(audio_stream.get("bit_rate"), fmt.get("bit_rate")),
    )
