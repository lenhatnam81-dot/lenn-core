"""Sinh thư viện nhạc giả lập bằng ffmpeg để test scanner/API/player mà
không cần file nhạc thật (môi trường CI/sandbox không có file nhạc mẫu).

Cấu trúc thư viện demo sinh ra:

  <root>/Artist One/Album Alpha/01 - Song One.flac
  <root>/Artist One/Album Alpha/02 - Song Two.flac
  <root>/Artist Two/Album Beta/01 - Song Three.mp3
"""

from __future__ import annotations

import subprocess
from pathlib import Path

TRACK_SPECS = [
    # (subpath, title, artist, album, album_artist, track_no, year, codec_args, ext)
    ("Artist One/Album Alpha/01 - Song One.flac", "Song One", "Artist One", "Album Alpha",
     "Artist One", "1", "2021", ["-c:a", "flac"], "flac"),
    ("Artist One/Album Alpha/02 - Song Two.flac", "Song Two", "Artist One", "Album Alpha",
     "Artist One", "2", "2021", ["-c:a", "flac"], "flac"),
    ("Artist Two/Album Beta/01 - Song Three.mp3", "Song Three", "Artist Two", "Album Beta",
     "Artist Two", "1", "2022", ["-c:a", "libmp3lame", "-b:a", "128k"], "mp3"),
]


def build_sample_library(root: Path, duration_seconds: float = 1.5) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for subpath, title, artist, album, album_artist, track_no, year, codec_args, _ext in TRACK_SPECS:
        out_path = root / subpath
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration_seconds}",
            "-metadata", f"title={title}",
            "-metadata", f"artist={artist}",
            "-metadata", f"album={album}",
            "-metadata", f"album_artist={album_artist}",
            "-metadata", f"track={track_no}",
            "-metadata", f"date={year}",
            *codec_args,
            str(out_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
    return root
