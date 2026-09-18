"""Audio engine cho 1 đầu ra (zone), dựng trên ffmpeg subprocess.

Đúng nguyên lý RAAT/Roon nêu trong tài liệu kiến trúc (Phần 2): việc decode
định dạng (FLAC/DSD/ALAC/MP3...) luôn diễn ra ở phía Core, endpoint chỉ nhận
audio đã giải mã — ở Phase 0 (1 zone chạy ngay trên Core) điều này thể hiện
qua việc ffmpeg decode + xuất thẳng ra thiết bị ALSA cục bộ.

Giới hạn đã biết của bản MVP này (ghi rõ để không hiểu nhầm là thiết kế cuối
cùng — xem README mục "Giới hạn & hướng nâng cấp"):
- pause/resume dùng SIGSTOP/SIGCONT trên tiến trình ffmpeg (dừng cứng tiến
  trình) — hoạt động tốt nhưng không "mượt" bằng một engine chuyên dụng.
- seek() và set_volume() phải khởi động lại tiến trình ffmpeg tại vị trí mới
  vì ffmpeg không có kênh điều khiển realtime như mpv IPC.
- Backend "alsa" cần phần cứng ALSA thật (chạy trên Beast/Phoenix/Rogue).
  Môi trường dev/test không có sound card sẽ tự dùng backend "file" (ghi ra
  .wav) để vẫn kiểm chứng được toàn bộ pipeline decode/điều khiển.

Khi cần tối ưu bit-perfect/độ trễ thấp hơn nữa, đây chính là chỗ để thay
bằng engine C++/Rust riêng (LAT) như đề xuất trong lộ trình Phase 3.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import signal
from pathlib import Path

logger = logging.getLogger("lenn_core.player")

_PROGRESS_RE = re.compile(r"out_time_ms=(\d+)")


def detect_default_backend() -> str:
    """Có ALSA card thật không? Nếu không (như trong sandbox này), dùng
    backend 'file' để pipeline vẫn chạy được và kiểm tra được."""
    return "alsa" if Path("/proc/asound").exists() else "file"


class FfmpegEngine:
    """Điều khiển việc phát 1 file audio qua ffmpeg cho một zone."""

    def __init__(self, zone_id: str, backend: str = "auto", alsa_device: str = "default",
                 file_backend_dir: str = "data/zone_output"):
        self.zone_id = zone_id
        self.backend = detect_default_backend() if backend == "auto" else backend
        self.alsa_device = alsa_device
        self.file_backend_dir = file_backend_dir
        Path(file_backend_dir).mkdir(parents=True, exist_ok=True)

        self._proc: asyncio.subprocess.Process | None = None
        self._progress_task: asyncio.Task | None = None
        self._current_path: str | None = None
        self._seek_offset: float = 0.0       # vị trí đã tua tới khi (re)start process
        self._elapsed_in_proc: float = 0.0   # số giây process hiện tại đã chạy được
        self._volume_percent: int = 80
        self._paused: bool = False
        self._manual_stop: bool = False
        self.on_position = lambda seconds: None      # callback do Zone gán
        self.on_track_ended = lambda: None            # callback do Zone gán (hết bài tự nhiên)

    @property
    def position_seconds(self) -> float:
        return self._seek_offset + self._elapsed_in_proc

    def _output_args(self) -> list[str]:
        if self.backend == "alsa":
            return ["-f", "alsa", self.alsa_device]
        if self.backend == "null":
            return ["-f", "null", "-"]
        # "file": ghi PCM thật ra wav để có thể nghe lại / test — hữu ích khi
        # dev không có sound card.
        out_path = str(Path(self.file_backend_dir) / f"{self.zone_id}.wav")
        return ["-y", out_path]

    async def _spawn(self, path: str, start_seconds: float, volume_percent: int) -> None:
        await self._kill_current()
        volume_factor = max(0.0, min(2.0, volume_percent / 100))
        cmd = [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-progress", "pipe:1", "-nostats",
            "-ss", f"{start_seconds:.3f}",
            "-re",  # đọc input theo đúng tốc độ thật (giống phát thời gian thực);
                     # với backend alsa thì thiết bị tự chặn tốc độ này, nhưng
                     # với backend "file"/"null" (dev/test) cờ này bắt buộc để
                     # không giải mã "chạy vượt" toàn bộ file trong tích tắc.
            "-i", path,
            "-vn",
            "-af", f"volume={volume_factor:.3f}",
            *self._output_args(),
        ]
        logger.info("zone=%s spawn: %s", self.zone_id, " ".join(cmd))
        self._proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        self._current_path = path
        self._seek_offset = start_seconds
        self._elapsed_in_proc = 0.0
        self._volume_percent = volume_percent
        self._paused = False
        self._manual_stop = False
        self._progress_task = asyncio.create_task(self._read_progress())
        asyncio.create_task(self._wait_and_notify(self._proc))

    async def _wait_and_notify(self, proc: "asyncio.subprocess.Process") -> None:
        returncode = await proc.wait()
        if proc is self._proc and not self._manual_stop and returncode == 0:
            # ffmpeg tự kết thúc vì hết file (EOF), không phải do ta chủ động dừng
            self.on_track_ended()

    async def _read_progress(self) -> None:
        assert self._proc and self._proc.stdout
        try:
            async for line in self._proc.stdout:
                m = _PROGRESS_RE.search(line.decode(errors="ignore"))
                if m:
                    self._elapsed_in_proc = int(m.group(1)) / 1_000_000
                    self.on_position(self.position_seconds)
        except Exception:
            logger.debug("progress reader kết thúc cho zone=%s", self.zone_id)

    async def _kill_current(self) -> None:
        self._manual_stop = True
        if self._progress_task:
            self._progress_task.cancel()
            self._progress_task = None
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=3)
            except (ProcessLookupError, asyncio.TimeoutError):
                try:
                    self._proc.kill()
                except ProcessLookupError:
                    pass
        self._proc = None

    # ---------- API điều khiển (dùng bởi Zone) ----------

    async def play(self, path: str, start_seconds: float = 0.0, volume_percent: int | None = None) -> None:
        await self._spawn(path, start_seconds, volume_percent if volume_percent is not None else self._volume_percent)

    async def stop(self) -> None:
        await self._kill_current()
        self._current_path = None
        self._seek_offset = 0.0
        self._elapsed_in_proc = 0.0

    async def pause(self) -> None:
        if self._proc and self._proc.returncode is None and not self._paused:
            try:
                self._proc.send_signal(signal.SIGSTOP)
                self._paused = True
            except ProcessLookupError:
                pass

    async def resume(self) -> None:
        if self._proc and self._proc.returncode is None and self._paused:
            try:
                self._proc.send_signal(signal.SIGCONT)
                self._paused = False
            except ProcessLookupError:
                pass

    async def seek(self, seconds: float) -> None:
        if self._current_path is None:
            return
        was_paused = self._paused
        await self._spawn(self._current_path, seconds, self._volume_percent)
        if was_paused:
            await self.pause()

    async def set_volume(self, volume_percent: int) -> None:
        """MVP: khởi động lại ffmpeg tại vị trí hiện tại với volume mới.
        Gây gián đoạn rất ngắn (vài chục ms) — chấp nhận được cho Phase 0,
        sẽ thay bằng mixing phần mềm realtime khi nâng cấp engine."""
        if self._current_path is None:
            self._volume_percent = volume_percent
            return
        was_paused = self._paused
        await self._spawn(self._current_path, self.position_seconds, volume_percent)
        if was_paused:
            await self.pause()

    def is_playing(self) -> bool:
        return self._proc is not None and self._proc.returncode is None and not self._paused

    def is_paused(self) -> bool:
        return self._paused

    def has_finished(self) -> bool:
        return self._proc is not None and self._proc.returncode is not None
