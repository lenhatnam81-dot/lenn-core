"""Endpoint SSE (/events) — kênh đẩy real-time cho Display API (Phần 7) và
LENN Remote (Phần 6), thay cho WebSocket.

Ghi chú kỹ thuật: bản MVP dùng Server-Sent Events (qua sse-starlette, đã có
sẵn trong môi trường) thay vì WebSocket, vì gói `websockets`/`wsproto` mà
uvicorn cần không cài được (chính sách mạng chặn pypi.org lúc build bản này).
SSE vẫn là kênh push một chiều Core -> client tiêu chuẩn, đủ dùng cho
now-playing/trạng thái zone; khi môi trường triển khai thật cho phép cài
`websockets`, có thể bổ sung endpoint WebSocket song song mà không phải đổi
kiến trúc — client Display/Remote chỉ cần fallback từ SSE sang WS.
"""

from __future__ import annotations

import asyncio

from sse_starlette.sse import EventSourceResponse
from starlette.requests import Request

from lenn_core.events import bus


async def stream_events(request: Request):
    queue = bus.subscribe()

    async def event_generator():
        try:
            yield {"event": "connected", "data": "{}"}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield {"event": event.type, "data": _to_json(event.data)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            bus.unsubscribe(queue)

    return EventSourceResponse(event_generator())


def _to_json(data: dict) -> str:
    import json
    return json.dumps(data, ensure_ascii=False)
