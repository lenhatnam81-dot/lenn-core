"""Điểm ghép nối toàn bộ LENN Core Phase 0 thành 1 ứng dụng Starlette:
DB, scanner, watcher realtime, zone manager, discovery UDP, và các route
REST + SSE. `create_app()` được dùng bởi cả scripts/run.py (chạy thật) và
bộ test (chạy trong bộ nhớ, DB riêng cho từng test).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from lenn_core.api import library, playback
from lenn_core.api.events_routes import stream_events
from lenn_core.config import LennCoreConfig
from lenn_core.db import Database
from lenn_core.discovery import start_discovery_responder
from lenn_core.scanner import LibraryScanner
from lenn_core.watcher import LibraryWatcher
from lenn_core.zones import ZoneManager

logger = logging.getLogger("lenn_core.api")

# lenn_core/api/app.py -> lenn_core/api -> lenn_core -> thư mục gốc project
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WEB_INDEX = PROJECT_ROOT / "web" / "index.html"


async def health(request):
    return JSONResponse({"status": "ok", "service": "lenn-core", "version": "0.1.0-phase0"})


async def index(request):
    """Trang web điều khiển tối giản, không cần đăng nhập (LENN Core chỉ
    dùng trong mạng nội bộ của chính LENN Audio Design) — vừa để kiểm tra
    nhanh sau khi cài đặt, vừa là bản tham khảo cho LENN Remote sau này."""
    if not WEB_INDEX.exists():
        return JSONResponse({"status": "ok", "service": "lenn-core", "note": "web/index.html không tồn tại"})
    return FileResponse(WEB_INDEX)


def create_app(config: LennCoreConfig | None = None) -> Starlette:
    config = config or LennCoreConfig.load()
    db = Database(config.db_path)
    scanner = LibraryScanner(db)
    zone_manager = ZoneManager(config.zones, db)

    routes = [
        Route("/", index),
        Route("/health", health),

        Route("/library/roots", library.list_roots),
        Route("/library/roots", library.add_root, methods=["POST"]),
        Route("/library/roots", library.remove_root, methods=["DELETE"]),
        Route("/library/folders", library.list_folders),
        Route("/library/albums", library.list_albums),
        Route("/library/albums/{album_key}/tracks", library.get_album_tracks),
        Route("/library/artists", library.list_artists),
        Route("/library/tracks/{track_id:int}", library.get_track),
        Route("/library/search", library.search),
        Route("/library/scan", library.trigger_scan, methods=["POST"]),

        Route("/zones", playback.list_zones),
        Route("/zones/{zone_id}", playback.get_zone),
        Route("/zones/{zone_id}/now-playing", playback.now_playing),
        Route("/zones/{zone_id}/play", playback.play, methods=["POST"]),
        Route("/zones/{zone_id}/pause", playback.pause, methods=["POST"]),
        Route("/zones/{zone_id}/resume", playback.resume, methods=["POST"]),
        Route("/zones/{zone_id}/stop", playback.stop, methods=["POST"]),
        Route("/zones/{zone_id}/seek", playback.seek, methods=["POST"]),
        Route("/zones/{zone_id}/volume", playback.set_volume, methods=["POST"]),
        Route("/zones/{zone_id}/next", playback.next_track, methods=["POST"]),
        Route("/zones/{zone_id}/previous", playback.previous_track, methods=["POST"]),
        Route("/zones/{zone_id}/queue", playback.add_queue, methods=["POST"]),

        Route("/events", stream_events),
    ]

    middleware = [
        Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]),
    ]

    @asynccontextmanager
    async def lifespan(app: Starlette):
        if config.scan_on_startup and config.library_roots:
            logger.info("Quét thư viện lúc khởi động...")
            stats = await asyncio.to_thread(scanner.full_scan, config.library_roots)
            logger.info("Quét xong: %s", stats)

        if config.watch_realtime:
            # Luôn tạo & start watcher kể cả khi library_roots đang RỖNG lúc
            # khởi động (đúng trường hợp máy vừa cài xong từ ISO, chưa có
            # thư viện nào) — để add_root() qua web sau này có một watcher
            # đang sống để gắn thêm watch vào, không cần khởi động lại service.
            loop = asyncio.get_running_loop()
            watcher = LibraryWatcher(scanner, config.library_roots)
            watcher.start(loop)
            app.state.watcher = watcher

        try:
            app.state.discovery_transport = await start_discovery_responder(config.http_port)
        except OSError:
            logger.warning("Không mở được cổng UDP discovery (%s) — bỏ qua tự động phát hiện.",
                            config.http_port)
            app.state.discovery_transport = None

        yield

        # Dừng sạch mọi tiến trình ffmpeg đang phát trước khi thoát — nếu
        # không, khi service bị `systemctl stop`/SIGTERM, các zone đang phát
        # sẽ để lại tiến trình ffmpeg mồ côi thay vì tắt cùng LENN Core.
        for zone in zone_manager.zones.values():
            await zone.stop()

        if app.state.watcher:
            app.state.watcher.stop()
        if app.state.discovery_transport:
            app.state.discovery_transport.close()

    app = Starlette(routes=routes, middleware=middleware, lifespan=lifespan)
    app.state.config = config
    app.state.db = db
    app.state.scanner = scanner
    app.state.zone_manager = zone_manager
    app.state.watcher = None
    app.state.discovery_transport = None

    return app
