"""Test scanner: quét thư viện giả lập, kiểm tra cả 2 chỉ mục (metadata +
folder) đều đúng. Dùng unittest (thư viện chuẩn) thay vì pytest vì môi
trường build hiện tại không cài được gói pip mới (xem README)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import build_sample_library
from lenn_core.db import Database
from lenn_core.metadata import probe_file
from lenn_core.scanner import LibraryScanner


class TestMetadataProbe(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        build_sample_library(self.tmpdir)

    def test_probe_flac_tags(self):
        f = self.tmpdir / "Artist One/Album Alpha/01 - Song One.flac"
        meta = probe_file(f)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.title, "Song One")
        self.assertEqual(meta.artist, "Artist One")
        self.assertEqual(meta.album, "Album Alpha")
        self.assertEqual(meta.track_no, 1)
        self.assertEqual(meta.year, 2021)
        self.assertEqual(meta.codec, "flac")
        self.assertGreater(meta.sample_rate, 0)
        self.assertGreater(meta.duration_seconds, 0)

    def test_probe_mp3_tags(self):
        f = self.tmpdir / "Artist Two/Album Beta/01 - Song Three.mp3"
        meta = probe_file(f)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.album, "Album Beta")
        self.assertEqual(meta.codec, "mp3")


class TestLibraryScanner(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        build_sample_library(self.tmpdir)
        self.db = Database(str(self.tmpdir / "test.db"))
        self.scanner = LibraryScanner(self.db)

    def test_full_scan_indexes_all_tracks(self):
        stats = self.scanner.full_scan([str(self.tmpdir)])
        self.assertEqual(stats["roots"], 1)
        self.assertEqual(stats["files_indexed"], 3)
        self.assertEqual(stats["errors"], 0)

        tracks = self.db.query("SELECT * FROM tracks ORDER BY title")
        self.assertEqual(len(tracks), 3)
        titles = {t["title"] for t in tracks}
        self.assertEqual(titles, {"Song One", "Song Two", "Song Three"})

    def test_folder_tree_built_correctly(self):
        self.scanner.full_scan([str(self.tmpdir)])
        folders = self.db.query("SELECT * FROM folders")
        paths = {f["path"] for f in folders}
        self.assertIn(str(self.tmpdir.resolve()), paths)
        self.assertTrue(any(p.endswith("Artist One") for p in paths))
        self.assertTrue(any(p.endswith("Album Alpha") for p in paths))

        album_alpha = self.db.query_one(
            "SELECT * FROM folders WHERE path = ?", (str((self.tmpdir / "Artist One/Album Alpha").resolve()),)
        )
        self.assertIsNotNone(album_alpha)
        tracks_in_album = self.db.query(
            "SELECT * FROM tracks WHERE folder_id = ?", (album_alpha["id"],)
        )
        self.assertEqual(len(tracks_in_album), 2)

    def test_rescan_is_idempotent_and_skips_unchanged(self):
        stats1 = self.scanner.full_scan([str(self.tmpdir)])
        stats2 = self.scanner.full_scan([str(self.tmpdir)])
        self.assertEqual(stats1["files_indexed"], 3)
        # Lần 2: file chưa đổi mtime/size -> không cần ffprobe lại -> 0 file "indexed"
        self.assertEqual(stats2["files_indexed"], 0)
        total_tracks = self.db.query_one("SELECT COUNT(*) AS c FROM tracks")
        self.assertEqual(total_tracks["c"], 3)  # không bị nhân đôi

    def test_remove_file_updates_index(self):
        self.scanner.full_scan([str(self.tmpdir)])
        target = self.tmpdir / "Artist One/Album Alpha/01 - Song One.flac"
        self.scanner.remove_file(target)
        row = self.db.query_one("SELECT * FROM tracks WHERE path = ?", (str(target),))
        self.assertIsNone(row)


if __name__ == "__main__":
    unittest.main()
