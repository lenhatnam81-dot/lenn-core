"""Test trực tiếp audio engine (FfmpegEngine + Zone), không qua HTTP —
dùng unittest.IsolatedAsyncioTestCase (thư viện chuẩn, không cần
pytest-asyncio) vì play/pause/seek đều là coroutine.

Test quan trọng nhất: khi 1 bài hát tự kết thúc (hết file), zone phải tự
động chuyển sang bài kế tiếp trong hàng đợi mà không cần Remote gọi API
/next — đây là hành vi cốt lõi của một "audio engine" thật, không chỉ là
API giả lập trạng thái.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import build_sample_library
from lenn_core.config import ZoneConfig
from lenn_core.db import Database
from lenn_core.scanner import LibraryScanner
from lenn_core.zones import PlayState, Zone


class TestZonePlayback(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        build_sample_library(self.tmpdir, duration_seconds=1.2)  # bài ngắn để test nhanh
        self.db = Database(str(self.tmpdir / "test.db"))
        scanner = LibraryScanner(self.db)
        scanner.full_scan([str(self.tmpdir)])
        self.zone = Zone(ZoneConfig(id="main", name="Main Zone", output_backend="file"), self.db)
        self.track_ids = [r["id"] for r in self.db.query("SELECT id FROM tracks ORDER BY title")]

    async def asyncTearDown(self):
        await self.zone.stop()

    async def test_play_produces_decoded_audio_file(self):
        await self.zone.play_queue([self.track_ids[0]])
        self.assertEqual(self.zone.state.state, PlayState.PLAYING)
        await asyncio.sleep(1.6)  # dài hơn thời lượng bài test (1.2s) để ffmpeg flush xong file
        out_wav = Path("data/zone_output/main.wav")
        self.assertTrue(out_wav.exists(), "ffmpeg phải ghi ra file wav (backend='file')")
        self.assertGreater(out_wav.stat().st_size, 1000, "file wav phải có dữ liệu audio thật")

    async def test_pause_resume(self):
        await self.zone.play_queue([self.track_ids[0]])
        await self.zone.pause()
        self.assertEqual(self.zone.state.state, PlayState.PAUSED)
        pos_while_paused = self.zone.state.position_seconds
        await asyncio.sleep(0.5)
        # Đã pause thật (SIGSTOP) -> ffmpeg không tiến thêm -> vị trí không đổi đáng kể
        self.assertAlmostEqual(self.zone.engine.position_seconds, pos_while_paused, delta=0.05)
        await self.zone.resume()
        self.assertEqual(self.zone.state.state, PlayState.PLAYING)

    async def test_auto_advance_to_next_track_when_song_ends(self):
        # 2 bài đầu đều thuộc Album Alpha (Song One, Song Two), mỗi bài ~1.2s
        await self.zone.play_queue(self.track_ids[:2], start_index=0)
        first_title = self.zone.state.current_track["title"]

        # Chờ hết bài 1 (ffmpeg tự thoát -> Zone._on_track_ended -> next() tự động)
        for _ in range(40):  # tối đa ~4s
            await asyncio.sleep(0.1)
            if self.zone.state.current_track and self.zone.state.current_track["title"] != first_title:
                break

        self.assertNotEqual(self.zone.state.current_track["title"], first_title,
                             "Zone phải tự chuyển bài khi bài trước hết, không cần gọi /next")
        self.assertEqual(self.zone.state.queue_index, 1)


if __name__ == "__main__":
    unittest.main()
