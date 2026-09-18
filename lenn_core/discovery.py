"""Tự động phát hiện LENN Core trong mạng LAN cho LENN Remote (Phần 6).

Tài liệu kiến trúc đề xuất mDNS/Bonjour (giống Roon Remote tự tìm Roon
Core). Gói `zeroconf` chuẩn cho việc đó không cài được trong môi trường build
này (chặn pypi.org), nên bản MVP dùng một cơ chế UDP broadcast tự viết,
không phụ thuộc thư viện ngoài — tương đương về chức năng ở quy mô LAN gia
đình:

  1. App di động gửi gói UDP broadcast "LENN_DISCOVER_V1" tới cổng 51000.
  2. Mỗi LENN Core đang chạy trả lời unicast JSON {name, core_id, http_port}.
  3. App liệt kê các Core trả lời được, cho người dùng chọn (thường chỉ có 1).

Khi triển khai thật và có thể cài `zeroconf`, nên thay/song song bằng mDNS
chuẩn để tương thích thêm với các công cụ khám phá thiết bị khác trong nhà
(Home Assistant, v.v.) — phần này không đụng tới bất kỳ API nào khác.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

logger = logging.getLogger("lenn_core.discovery")

DISCOVERY_PORT = 51000
DISCOVERY_MAGIC = "LENN_DISCOVER_V1"


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, core_name: str, core_id: str, http_port: int):
        self.core_name = core_name
        self.core_id = core_id
        self.http_port = http_port
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        if data.decode(errors="ignore").strip() != DISCOVERY_MAGIC:
            return
        payload = json.dumps({
            "name": self.core_name,
            "core_id": self.core_id,
            "http_port": self.http_port,
        }).encode("utf-8")
        if self.transport:
            self.transport.sendto(payload, addr)
            logger.debug("Trả lời discovery cho %s", addr)


async def start_discovery_responder(http_port: int, core_name: str = "LENN Core") -> asyncio.DatagramTransport:
    loop = asyncio.get_running_loop()
    core_id = str(uuid.uuid4())
    transport, _protocol = await loop.create_datagram_endpoint(
        lambda: _DiscoveryProtocol(core_name, core_id, http_port),
        local_addr=("0.0.0.0", DISCOVERY_PORT),
        allow_broadcast=True,
    )
    logger.info("Discovery responder đang lắng nghe UDP :%s", DISCOVERY_PORT)
    return transport
