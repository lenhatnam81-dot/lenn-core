"""Event bus nội bộ, đơn giản: pub/sub trên asyncio.Queue.

Dùng để đẩy sự kiện real-time (đổi bài, đổi trạng thái play/pause, đổi
queue, thư viện có track mới...) tới mọi client đang lắng nghe qua SSE
(`/events`) — đây là phần lõi phục vụ Phần 7 (Display API) và giúp LENN
Remote (Phần 6) không cần polling liên tục.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


class EventBus:
    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def publish(self, type_: str, data: dict[str, Any] | None = None) -> None:
        event = Event(type=type_, data=data or {})
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # client chậm/đứng hình: bỏ event cũ nhất để không chặn hệ thống
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except asyncio.QueueEmpty:
                    pass


# Instance dùng chung toàn app (đủ cho Phase 0, một tiến trình duy nhất)
bus = EventBus()
