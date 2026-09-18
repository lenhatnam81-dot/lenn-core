"""Zone = một đầu ra âm thanh có thể điều khiển độc lập (Phần 2 trong tài
liệu kiến trúc). Phase 0 chạy 1 (hoặc vài) zone ngay trên chính LENN Core;
kiến trúc để hở chỗ cho Phase 1+ thay lớp truyền tải bằng Snapcast/LAT để
đồng bộ nhiều zone thật sự phân tán, mà không phải đổi API phía trên.

Zone giữ: hàng đợi phát (queue) gồm các track_id, vị trí hiện tại trong
queue, trạng thái phát (stopped/playing/paused), volume — và phát sự kiện
lên EventBus mỗi khi có thay đổi để LENN Remote / Display API (Phần 6, 7)
nhận real-time qua SSE mà không cần polling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from lenn_core.config import ZoneConfig
from lenn_core.db import Database
from lenn_core.events import bus
from lenn_core.player import FfmpegEngine

logger = logging.getLogger("lenn_core.zones")


class PlayState(str, Enum):
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"


@dataclass
class ZoneState:
    id: str
    name: str
    state: PlayState = PlayState.STOPPED
    queue: list[int] = field(default_factory=list)
    queue_index: int = -1
    position_seconds: float = 0.0
    volume: int = 80
    current_track: dict | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state.value,
            "queue": self.queue,
            "queue_index": self.queue_index,
            "position_seconds": round(self.position_seconds, 2),
            "volume": self.volume,
            "current_track": self.current_track,
        }


class Zone:
    def __init__(self, config: ZoneConfig, db: Database):
        self.db = db
        self.state = ZoneState(id=config.id, name=config.name, volume=80)
        self.engine = FfmpegEngine(
            zone_id=config.id, backend=config.output_backend, alsa_device=config.alsa_device,
        )
        self.engine.on_position = self._on_position
        self.engine.on_track_ended = self._on_track_ended

    def _emit(self, type_: str) -> None:
        bus.publish(type_, {"zone": self.state.to_dict()})

    def _on_position(self, seconds: float) -> None:
        self.state.position_seconds = seconds
        # Không emit event cho mỗi mốc tiến trình (quá dày) — Remote/Display
        # có thể GET /zones/{id} định kỳ nhẹ nhàng, hoặc ta có thể throttle
        # sau này. Sự kiện đầy đủ được bắn khi đổi bài/trạng thái.

    def _on_track_ended(self) -> None:
        import asyncio
        asyncio.create_task(self.next())

    def _track_row_to_dict(self, row) -> dict:
        return {
            "id": row["id"], "path": row["path"], "title": row["title"],
            "artist": row["artist"], "album": row["album"], "album_artist": row["album_artist"],
            "track_no": row["track_no"], "duration_seconds": row["duration_seconds"],
            "codec": row["codec"], "sample_rate": row["sample_rate"], "bit_depth": row["bit_depth"],
            "channels": row["channels"], "bitrate": row["bitrate"],
        }

    def _get_track(self, track_id: int):
        return self.db.query_one("SELECT * FROM tracks WHERE id = ?", (track_id,))

    async def play_queue(self, track_ids: list[int], start_index: int = 0) -> None:
        if not track_ids:
            return
        self.state.queue = track_ids
        self.state.queue_index = max(0, min(start_index, len(track_ids) - 1))
        await self._play_current()

    async def _play_current(self) -> None:
        if not (0 <= self.state.queue_index < len(self.state.queue)):
            await self.stop()
            return
        track_id = self.state.queue[self.state.queue_index]
        row = self._get_track(track_id)
        if row is None:
            logger.warning("zone=%s track_id=%s không còn tồn tại, bỏ qua", self.state.id, track_id)
            await self.next()
            return
        self.state.current_track = self._track_row_to_dict(row)
        self.state.state = PlayState.PLAYING
        self.state.position_seconds = 0.0
        await self.engine.play(row["path"], start_seconds=0.0, volume_percent=self.state.volume)
        self._emit("now_playing_changed")

    async def pause(self) -> None:
        if self.state.state == PlayState.PLAYING:
            await self.engine.pause()
            self.state.state = PlayState.PAUSED
            self._emit("playback_state_changed")

    async def resume(self) -> None:
        if self.state.state == PlayState.PAUSED:
            await self.engine.resume()
            self.state.state = PlayState.PLAYING
            self._emit("playback_state_changed")

    async def stop(self) -> None:
        await self.engine.stop()
        self.state.state = PlayState.STOPPED
        self.state.current_track = None
        self.state.position_seconds = 0.0
        self._emit("playback_state_changed")

    async def seek(self, seconds: float) -> None:
        if self.state.current_track is None:
            return
        await self.engine.seek(seconds)
        self.state.position_seconds = seconds
        self._emit("playback_state_changed")

    async def set_volume(self, volume: int) -> None:
        volume = max(0, min(100, volume))
        self.state.volume = volume
        await self.engine.set_volume(volume)
        self._emit("playback_state_changed")

    async def next(self) -> None:
        if self.state.queue_index + 1 < len(self.state.queue):
            self.state.queue_index += 1
            await self._play_current()
        else:
            await self.stop()

    async def previous(self) -> None:
        if self.state.queue_index > 0:
            self.state.queue_index -= 1
            await self._play_current()

    async def add_to_queue(self, track_ids: list[int]) -> None:
        was_empty = not self.state.queue
        self.state.queue.extend(track_ids)
        self._emit("queue_changed")
        if was_empty:
            self.state.queue_index = 0
            await self._play_current()


class ZoneManager:
    def __init__(self, configs: list[ZoneConfig], db: Database):
        self.zones: dict[str, Zone] = {c.id: Zone(c, db) for c in configs}

    def get(self, zone_id: str) -> Zone | None:
        return self.zones.get(zone_id)

    def list(self) -> list[dict]:
        return [z.state.to_dict() for z in self.zones.values()]
