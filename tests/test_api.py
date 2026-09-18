"""Test API REST bằng Starlette TestClient (chạy trên httpx, không cần
server thật). Dùng thư viện giả lập sinh bởi fixtures.build_sample_library."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from starlette.testclient import TestClient

from fixtures import build_sample_library
from lenn_core.api.app import create_app
from lenn_core.config import LennCoreConfig, ZoneConfig


def _make_client(tmpdir: Path) -> TestClient:
    config = LennCoreConfig(
        library_roots=[str(tmpdir)],
        db_path=str(tmpdir / "lenn_core.db"),
        zones=[ZoneConfig(id="main", name="Main Zone", output_backend="file")],
        http_port=8123,
        scan_on_startup=True,
        watch_realtime=False,  # tránh watchdog thread trong test, không cần thiết ở đây
    )
    app = create_app(config)
    return TestClient(app)


class TestLibraryApi(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        build_sample_library(self.tmpdir)
        self.client = _make_client(self.tmpdir)
        self.client.__enter__()  # kích hoạt lifespan (chạy full_scan lúc startup)

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_albums_listed_after_startup_scan(self):
        r = self.client.get("/library/albums")
        self.assertEqual(r.status_code, 200)
        albums = {a["album"] for a in r.json()["albums"]}
        self.assertEqual(albums, {"Album Alpha", "Album Beta"})

    def test_artists_listed(self):
        r = self.client.get("/library/artists")
        artists = {a["name"] for a in r.json()["artists"]}
        self.assertEqual(artists, {"Artist One", "Artist Two"})

    def test_album_tracks_by_key(self):
        albums = self.client.get("/library/albums").json()["albums"]
        alpha = next(a for a in albums if a["album"] == "Album Alpha")
        r = self.client.get(f"/library/albums/{alpha['album_key']}/tracks")
        self.assertEqual(r.status_code, 200)
        titles = [t["title"] for t in r.json()["tracks"]]
        self.assertEqual(titles, ["Song One", "Song Two"])  # đúng thứ tự track_no

    def test_folder_browser_root_and_drill_down(self):
        root = self.client.get("/library/folders").json()
        self.assertEqual(len(root["folders"]), 1)  # 1 thư mục gốc (tmpdir)

        level1 = self.client.get("/library/folders", params={"path": root["folders"][0]["path"]}).json()
        subfolder_names = {f["name"] for f in level1["folders"]}
        self.assertEqual(subfolder_names, {"Artist One", "Artist Two"})

        artist_one = next(f for f in level1["folders"] if f["name"] == "Artist One")
        level2 = self.client.get("/library/folders", params={"path": artist_one["path"]}).json()
        self.assertEqual([f["name"] for f in level2["folders"]], ["Album Alpha"])

        album_alpha = level2["folders"][0]
        level3 = self.client.get("/library/folders", params={"path": album_alpha["path"]}).json()
        self.assertEqual(len(level3["tracks"]), 2)

    def test_search(self):
        r = self.client.get("/library/search", params={"q": "Song Two"})
        data = r.json()
        self.assertEqual(len(data["tracks"]), 1)
        self.assertEqual(data["tracks"][0]["title"], "Song Two")

    def test_zones_listed(self):
        r = self.client.get("/zones")
        zones = r.json()["zones"]
        self.assertEqual(len(zones), 1)
        self.assertEqual(zones[0]["id"], "main")
        self.assertEqual(zones[0]["state"], "stopped")


class TestPlaybackApi(unittest.TestCase):
    """Kiểm tra vòng đời play/pause/resume/stop qua API — dùng backend
    'file' (không cần sound card thật) nên chạy được trong sandbox."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        build_sample_library(self.tmpdir)
        self.client = _make_client(self.tmpdir)
        self.client.__enter__()
        track = self.client.get("/library/search", params={"q": "Song One"}).json()["tracks"][0]
        self.track_id = track["id"]

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_play_pause_resume_stop(self):
        r = self.client.post("/zones/main/play", json={"track_id": self.track_id})
        self.assertEqual(r.status_code, 200)
        state = r.json()
        self.assertEqual(state["state"], "playing")
        self.assertEqual(state["current_track"]["title"], "Song One")

        r = self.client.post("/zones/main/pause")
        self.assertEqual(r.json()["state"], "paused")

        r = self.client.post("/zones/main/resume")
        self.assertEqual(r.json()["state"], "playing")

        r = self.client.post("/zones/main/stop")
        self.assertEqual(r.json()["state"], "stopped")
        self.assertIsNone(r.json()["current_track"])

    def test_volume_and_now_playing(self):
        self.client.post("/zones/main/play", json={"track_id": self.track_id})
        r = self.client.post("/zones/main/volume", json={"volume": 50})
        self.assertEqual(r.json()["volume"], 50)

        r = self.client.get("/zones/main/now-playing")
        data = r.json()
        self.assertEqual(data["volume"], 50)
        self.assertEqual(data["track"]["title"], "Song One")
        self.client.post("/zones/main/stop")

    def test_queue_next_previous(self):
        tracks = self.client.get("/library/albums").json()["albums"]
        alpha = next(a for a in tracks if a["album"] == "Album Alpha")
        album_tracks = self.client.get(f"/library/albums/{alpha['album_key']}/tracks").json()["tracks"]
        ids = [t["id"] for t in album_tracks]

        r = self.client.post("/zones/main/play", json={"track_ids": ids, "start_index": 0})
        self.assertEqual(r.json()["current_track"]["title"], "Song One")

        r = self.client.post("/zones/main/next")
        self.assertEqual(r.json()["current_track"]["title"], "Song Two")

        r = self.client.post("/zones/main/previous")
        self.assertEqual(r.json()["current_track"]["title"], "Song One")
        self.client.post("/zones/main/stop")


if __name__ == "__main__":
    unittest.main()
