"""API điều khiển phát nhạc theo zone — mặt REST mà LENN Remote (Phần 6)
gọi tới. Toàn bộ audio thật sự chạy trong LENN Core; app điện thoại chỉ gửi
lệnh, đúng nguyên tắc "Remote không xử lý audio" trong tài liệu kiến trúc.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse


def _zone_or_404(request: Request):
    zone_manager = request.app.state.zone_manager
    zone = zone_manager.get(request.path_params["zone_id"])
    return zone


async def list_zones(request: Request) -> JSONResponse:
    return JSONResponse({"zones": request.app.state.zone_manager.list()})


async def get_zone(request: Request) -> JSONResponse:
    zone = _zone_or_404(request)
    if zone is None:
        return JSONResponse({"error": "zone_not_found"}, status_code=404)
    return JSONResponse(zone.state.to_dict())


async def now_playing(request: Request) -> JSONResponse:
    """Endpoint tối giản cho Display API (Phần 7): bài đang phát + tiến trình."""
    zone = _zone_or_404(request)
    if zone is None:
        return JSONResponse({"error": "zone_not_found"}, status_code=404)
    return JSONResponse({
        "zone_id": zone.state.id,
        "state": zone.state.state.value,
        "track": zone.state.current_track,
        "position_seconds": round(zone.state.position_seconds, 2),
        "volume": zone.state.volume,
    })


async def play(request: Request) -> JSONResponse:
    zone = _zone_or_404(request)
    if zone is None:
        return JSONResponse({"error": "zone_not_found"}, status_code=404)
    body = await request.json()
    if "track_id" in body:
        track_ids = [int(body["track_id"])]
        start_index = 0
    else:
        track_ids = [int(t) for t in body.get("track_ids", [])]
        start_index = int(body.get("start_index", 0))
    if not track_ids:
        return JSONResponse({"error": "no_tracks"}, status_code=400)
    await zone.play_queue(track_ids, start_index)
    return JSONResponse(zone.state.to_dict())


async def pause(request: Request) -> JSONResponse:
    zone = _zone_or_404(request)
    if zone is None:
        return JSONResponse({"error": "zone_not_found"}, status_code=404)
    await zone.pause()
    return JSONResponse(zone.state.to_dict())


async def resume(request: Request) -> JSONResponse:
    zone = _zone_or_404(request)
    if zone is None:
        return JSONResponse({"error": "zone_not_found"}, status_code=404)
    await zone.resume()
    return JSONResponse(zone.state.to_dict())


async def stop(request: Request) -> JSONResponse:
    zone = _zone_or_404(request)
    if zone is None:
        return JSONResponse({"error": "zone_not_found"}, status_code=404)
    await zone.stop()
    return JSONResponse(zone.state.to_dict())


async def seek(request: Request) -> JSONResponse:
    zone = _zone_or_404(request)
    if zone is None:
        return JSONResponse({"error": "zone_not_found"}, status_code=404)
    body = await request.json()
    await zone.seek(float(body["position_seconds"]))
    return JSONResponse(zone.state.to_dict())


async def set_volume(request: Request) -> JSONResponse:
    zone = _zone_or_404(request)
    if zone is None:
        return JSONResponse({"error": "zone_not_found"}, status_code=404)
    body = await request.json()
    await zone.set_volume(int(body["volume"]))
    return JSONResponse(zone.state.to_dict())


async def next_track(request: Request) -> JSONResponse:
    zone = _zone_or_404(request)
    if zone is None:
        return JSONResponse({"error": "zone_not_found"}, status_code=404)
    await zone.next()
    return JSONResponse(zone.state.to_dict())


async def previous_track(request: Request) -> JSONResponse:
    zone = _zone_or_404(request)
    if zone is None:
        return JSONResponse({"error": "zone_not_found"}, status_code=404)
    await zone.previous()
    return JSONResponse(zone.state.to_dict())


async def add_queue(request: Request) -> JSONResponse:
    zone = _zone_or_404(request)
    if zone is None:
        return JSONResponse({"error": "zone_not_found"}, status_code=404)
    body = await request.json()
    track_ids = [int(t) for t in body.get("track_ids", [])]
    await zone.add_to_queue(track_ids)
    return JSONResponse(zone.state.to_dict())
