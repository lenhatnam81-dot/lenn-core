"""Lớp truy cập SQLite cho LENN Core.

Hai chỉ mục song song trên cùng một bảng `tracks`:
- Chỉ mục metadata (album/artist/genre...) phục vụ view kiểu Roon.
- Chỉ mục folder (bảng `folders`, cây thư mục thật) phục vụ Folder Browser
  kiểu JRiver — xem Phần 4 trong tài liệu kiến trúc.

SQLite được chọn cho Phase 0 vì nhẹ, không cần server riêng, đủ nhanh cho thư
viện cá nhân cỡ lớn (Roon dùng mô hình tương tự — DB nhúng cục bộ trên Core).
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
    is_root INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_id);

CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    folder_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
    title TEXT,
    artist TEXT,
    album TEXT,
    album_artist TEXT,
    track_no INTEGER,
    disc_no INTEGER,
    year INTEGER,
    genre TEXT,
    duration_seconds REAL,
    codec TEXT,
    sample_rate INTEGER,
    bit_depth INTEGER,
    channels INTEGER,
    bitrate INTEGER,
    file_size INTEGER,
    file_mtime REAL,
    source TEXT NOT NULL DEFAULT 'local',
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tracks_folder ON tracks(folder_id);
CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album, album_artist);
CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(album_artist);
CREATE INDEX IF NOT EXISTS idx_tracks_title ON tracks(title);
"""


class Database:
    """Wrapper mỏng quanh sqlite3, an toàn cho dùng trong ứng dụng asyncio
    (mỗi thread/task lấy connection riêng qua threading.local)."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self) -> None:
        conn = self._connect()
        conn.executescript(SCHEMA)
        conn.commit()

    @contextmanager
    def cursor(self):
        conn = self._connect()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def execute(self, sql: str, params: tuple = ()) -> int:
        """Chạy INSERT/UPDATE/DELETE, trả về lastrowid (nếu có)."""
        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.lastrowid
