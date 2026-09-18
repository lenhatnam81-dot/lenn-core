"""Quét thư viện nhạc: dựng đồng thời chỉ mục folder thật (Phần 4 - JRiver
style) và chỉ mục metadata (Phần 1 - Roon style) trong cùng một lượt quét.

Hỗ trợ quét toàn bộ (full scan, dùng lúc khởi động hoặc khi bấm "Rescan")
và cập nhật từng file riêng lẻ (dùng bởi watcher.py khi có sự kiện realtime).

Vì mỗi thư mục trong `library_roots` chỉ là một đường dẫn trên filesystem,
scanner không quan tâm đó là ổ đĩa local hay NAS đã mount qua SMB/NFS (Phần
5) — miễn hệ điều hành đã mount xong trước khi LENN Core khởi động, hoặc
được thêm bằng API /library/roots sau khi mount.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from lenn_core.config import AUDIO_EXTENSIONS
from lenn_core.db import Database
from lenn_core.metadata import probe_file

logger = logging.getLogger("lenn_core.scanner")


class LibraryScanner:
    def __init__(self, db: Database):
        self.db = db

    # ---------- Folder index ----------

    def _upsert_folder(self, path: Path, is_root: bool) -> int:
        row = self.db.query_one("SELECT id FROM folders WHERE path = ?", (str(path),))
        if row:
            return row["id"]
        parent_id = None
        if not is_root:
            parent_row = self.db.query_one("SELECT id FROM folders WHERE path = ?", (str(path.parent),))
            parent_id = parent_row["id"] if parent_row else None
        return self.db.execute(
            "INSERT INTO folders (path, name, parent_id, is_root) VALUES (?, ?, ?, ?)",
            (str(path), path.name or str(path), parent_id, 1 if is_root else 0),
        )

    def ensure_folder_chain(self, folder_path: Path, root_path: Path) -> int:
        """Đảm bảo mọi thư mục cha từ root_path đến folder_path đều có trong
        bảng folders (để cây thư mục Folder Browser không bị đứt đoạn)."""
        folder_path = folder_path.resolve()
        root_path = root_path.resolve()
        parts_to_create: list[Path] = []
        cur = folder_path
        while True:
            row = self.db.query_one("SELECT id FROM folders WHERE path = ?", (str(cur),))
            if row:
                break
            parts_to_create.append(cur)
            if cur == root_path or cur.parent == cur:
                break
            cur = cur.parent
        for p in reversed(parts_to_create):
            self._upsert_folder(p, is_root=(p == root_path))
        row = self.db.query_one("SELECT id FROM folders WHERE path = ?", (str(folder_path),))
        return row["id"] if row else self._upsert_folder(folder_path, is_root=(folder_path == root_path))

    # ---------- Track index ----------

    def index_file(self, file_path: Path, root_path: Path) -> bool:
        """Quét/cập nhật 1 file nhạc. Trả về True nếu đã ghi/ cập nhật DB."""
        if file_path.suffix.lower() not in AUDIO_EXTENSIONS:
            return False
        try:
            stat = file_path.stat()
        except FileNotFoundError:
            return False

        existing = self.db.query_one(
            "SELECT id, file_mtime, file_size FROM tracks WHERE path = ?", (str(file_path),)
        )
        if existing and existing["file_mtime"] == stat.st_mtime and existing["file_size"] == stat.st_size:
            return False  # chưa đổi, khỏi ffprobe lại cho nhanh

        meta = probe_file(file_path)
        if meta is None:
            logger.warning("Không đọc được metadata: %s", file_path)
            return False

        folder_id = self.ensure_folder_chain(file_path.parent, root_path)
        title = meta.title or file_path.stem

        if existing:
            self.db.execute(
                """UPDATE tracks SET folder_id=?, title=?, artist=?, album=?, album_artist=?,
                   track_no=?, disc_no=?, year=?, genre=?, duration_seconds=?, codec=?,
                   sample_rate=?, bit_depth=?, channels=?, bitrate=?, file_size=?, file_mtime=?,
                   updated_at=datetime('now') WHERE id=?""",
                (folder_id, title, meta.artist, meta.album, meta.album_artist,
                 meta.track_no, meta.disc_no, meta.year, meta.genre, meta.duration_seconds,
                 meta.codec, meta.sample_rate, meta.bit_depth, meta.channels, meta.bitrate,
                 stat.st_size, stat.st_mtime, existing["id"]),
            )
        else:
            self.db.execute(
                """INSERT INTO tracks (path, folder_id, title, artist, album, album_artist,
                   track_no, disc_no, year, genre, duration_seconds, codec, sample_rate,
                   bit_depth, channels, bitrate, file_size, file_mtime)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(file_path), folder_id, title, meta.artist, meta.album, meta.album_artist,
                 meta.track_no, meta.disc_no, meta.year, meta.genre, meta.duration_seconds,
                 meta.codec, meta.sample_rate, meta.bit_depth, meta.channels, meta.bitrate,
                 stat.st_size, stat.st_mtime),
            )
        return True

    def remove_file(self, file_path: Path) -> None:
        self.db.execute("DELETE FROM tracks WHERE path = ?", (str(file_path),))

    def remove_folder(self, folder_path: Path) -> None:
        self.db.execute("DELETE FROM folders WHERE path = ?", (str(folder_path),))

    def full_scan(self, library_roots: list[str]) -> dict:
        """Quét toàn bộ danh sách thư mục gốc. Trả về thống kê để log/API."""
        stats = {"roots": 0, "files_seen": 0, "files_indexed": 0, "errors": 0}
        for root_str in library_roots:
            root = Path(root_str)
            if not root.exists():
                logger.warning("Thư mục thư viện không tồn tại (NAS chưa mount?): %s", root)
                stats["errors"] += 1
                continue
            self._upsert_folder(root.resolve(), is_root=True)
            stats["roots"] += 1
            for dirpath, _dirnames, filenames in os.walk(root):
                for fname in filenames:
                    fpath = Path(dirpath) / fname
                    stats["files_seen"] += 1
                    try:
                        if self.index_file(fpath, root):
                            stats["files_indexed"] += 1
                    except Exception:
                        logger.exception("Lỗi khi index file %s", fpath)
                        stats["errors"] += 1
        return stats
