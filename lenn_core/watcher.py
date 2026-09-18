"""Theo dõi thay đổi thư viện theo thời gian thực bằng watchdog.

watchdog chạy trên thread riêng (đúng thiết kế của thư viện), nên các sự
kiện được đẩy vào vòng lặp asyncio chính của LENN Core một cách an toàn qua
`loop.call_soon_threadsafe`.

Ghi chú (đã nêu trong tài liệu kiến trúc, Phần 5): inotify không phải lúc
nào cũng đáng tin cậy 100% qua các network mount (SMB/NFS cho thư viện NAS),
nên ngoài watcher realtime này, `full_scan()` định kỳ / theo yêu cầu vẫn nên
được gọi như lớp dự phòng.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from lenn_core.config import AUDIO_EXTENSIONS
from lenn_core.scanner import LibraryScanner

logger = logging.getLogger("lenn_core.watcher")


class _Handler(FileSystemEventHandler):
    def __init__(self, root: Path, scanner: LibraryScanner, loop: asyncio.AbstractEventLoop, on_change):
        self.root = root
        self.scanner = scanner
        self.loop = loop
        self.on_change = on_change

    def _is_audio(self, path_str: str) -> bool:
        return Path(path_str).suffix.lower() in AUDIO_EXTENSIONS

    def _schedule(self, fn, *args):
        self.loop.call_soon_threadsafe(fn, *args)

    def on_created(self, event):
        if not event.is_directory and self._is_audio(event.src_path):
            self._schedule(self._index, Path(event.src_path))

    def on_modified(self, event):
        if not event.is_directory and self._is_audio(event.src_path):
            self._schedule(self._index, Path(event.src_path))

    def on_deleted(self, event):
        if not event.is_directory and self._is_audio(event.src_path):
            self._schedule(self._remove, Path(event.src_path))
        elif event.is_directory:
            self._schedule(self._remove_folder, Path(event.src_path))

    def on_moved(self, event):
        if not event.is_directory and self._is_audio(event.src_path):
            self._schedule(self._remove, Path(event.src_path))
        if not event.is_directory and self._is_audio(event.dest_path):
            self._schedule(self._index, Path(event.dest_path))

    def _index(self, path: Path):
        try:
            changed = self.scanner.index_file(path, self.root)
            if changed:
                self.on_change("track_indexed", {"path": str(path)})
        except Exception:
            logger.exception("Lỗi index realtime cho %s", path)

    def _remove(self, path: Path):
        self.scanner.remove_file(path)
        self.on_change("track_removed", {"path": str(path)})

    def _remove_folder(self, path: Path):
        self.scanner.remove_folder(path)
        self.on_change("folder_removed", {"path": str(path)})


class LibraryWatcher:
    def __init__(self, scanner: LibraryScanner, library_roots: list[str], on_change=lambda *a: None):
        self.scanner = scanner
        self.library_roots = [Path(r) for r in library_roots]
        self.on_change = on_change
        self.observer = Observer()
        self._started = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._watches: dict[str, object] = {}  # path(str) -> ObservedWatch, để unschedule khi remove_root

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        for root in self.library_roots:
            self._schedule(root)
        if self._watches:
            self.observer.start()
            self._started = True

    def _schedule(self, root: Path) -> None:
        if not root.exists():
            logger.warning("Bỏ qua watch (chưa mount?): %s", root)
            return
        assert self._loop is not None
        handler = _Handler(root, self.scanner, self._loop, self.on_change)
        watch = self.observer.schedule(handler, str(root), recursive=True)
        self._watches[str(root)] = watch
        logger.info("Đang theo dõi realtime: %s", root)

    def add_root(self, root_str: str) -> None:
        """Thêm 1 thư mục để theo dõi realtime khi đang chạy (ví dụ người
        dùng vừa thêm thư viện qua trang web) — không cần khởi động lại
        service."""
        root = Path(root_str)
        if str(root) in self._watches:
            return
        if self._loop is None:
            return  # watcher chưa start() lần nào (watch_realtime=False) — bỏ qua
        self._schedule(root)
        if not self._started and self._watches:
            self.observer.start()
            self._started = True

    def remove_root(self, root_str: str) -> None:
        root = str(Path(root_str))
        watch = self._watches.pop(root, None)
        if watch is not None:
            self.observer.unschedule(watch)

    def stop(self) -> None:
        if self._started:
            self.observer.stop()
            self.observer.join(timeout=5)
