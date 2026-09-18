"""Test API thêm/xoá thư mục thư viện lúc đang chạy (POST/DELETE
/library/roots) — tính năng cho phép thiết lập ban đầu sau khi cài từ ISO
mà không cần SSH sửa config.json tay, và xác nhận watcher realtime được
gắn/gỡ đúng cho thư mục mới mà không cần khởi động lại service."""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from starlette.testclient import TestClient

from fixtures import build_sample_library
from lenn_core.api.app import create_app
from lenn_core.config import LennCoreConfig, ZoneConfig


class TestLibraryRootsApi(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.config_path = self.tmpdir / "config.json"
        # Cố tình để library_roots RỖNG lúc khởi động, giống máy vừa cài
        # xong từ ISO chưa có thư viện nào — đúng kịch bản cần tính năng này.
        config = LennCoreConfig(
            library_roots=[],
            db_path=str(self.tmpdir / "lenn_core.db"),
            zones=[ZoneConfig(id="main", name="Main Zone", output_backend="file")],
            scan_on_startup=True,
            watch_realtime=True,
        )
        config._config_path = str(self.config_path)
        self.app = create_app(config)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_add_root_scans_and_persists_to_config_json(self):
        lib_dir = self.tmpdir / "musiclib"
        build_sample_library(lib_dir)

        r = self.client.post("/library/roots", json={"path": str(lib_dir)})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["scan_stats"]["files_indexed"], 3)

        albums = self.client.get("/library/albums").json()["albums"]
        self.assertEqual({a["album"] for a in albums}, {"Album Alpha", "Album Beta"})

        # Đã ghi lại config.json trên đĩa (để service restart vẫn nhớ) —
        # đúng yêu cầu "không cần SSH sửa tay".
        self.assertTrue(self.config_path.exists())
        import json
        saved = json.loads(self.config_path.read_text())
        self.assertIn(str(lib_dir.resolve()), saved["library_roots"])

    def test_add_nonexistent_path_rejected(self):
        r = self.client.post("/library/roots", json={"path": "/khong/ton/tai/dau"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"], "path_not_found")

    def test_add_root_is_watched_realtime_without_restart(self):
        lib_dir = self.tmpdir / "musiclib2"
        build_sample_library(lib_dir)
        self.client.post("/library/roots", json={"path": str(lib_dir)})

        # Thêm 1 file MỚI sau khi đã add_root xong (mô phỏng người dùng chép
        # thêm nhạc vào) — watcher phải tự bắt được mà KHÔNG cần gọi lại
        # /library/scan hay khởi động lại service.
        import subprocess
        new_file = lib_dir / "Artist Three" / "Album Gamma" / "01 - New.flac"
        new_file.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=300:duration=1",
            "-metadata", "album=Album Gamma", "-metadata", "album_artist=Artist Three",
            "-c:a", "flac", str(new_file),
        ], check=True, capture_output=True)

        for _ in range(30):
            albums = self.client.get("/library/albums").json()["albums"]
            if any(a["album"] == "Album Gamma" for a in albums):
                break
            time.sleep(0.2)
        else:
            self.fail("Watcher không tự phát hiện file mới thêm vào thư mục vừa add_root")

    def test_remove_root(self):
        lib_dir = self.tmpdir / "musiclib3"
        build_sample_library(lib_dir)
        self.client.post("/library/roots", json={"path": str(lib_dir)})

        r = self.client.request("DELETE", "/library/roots", json={"path": str(lib_dir)})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn(str(lib_dir.resolve()), r.json()["library_roots"])


if __name__ == "__main__":
    unittest.main()
