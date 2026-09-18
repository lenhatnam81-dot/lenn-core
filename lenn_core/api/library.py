"""API duyệt thư viện: 2 chế độ song song đúng như Phần 1 & Phần 4 của tài
liệu kiến trúc —
  - Library view (album/artist), metadata-driven, kiểu Roon.
  - Folder view, cây thư mục thật, kiểu JRiver.
Cộng thêm tìm kiếm và điều khiển quét thư viện (thủ công / NAS mới mount).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse


def _album_key(album: str | None, album_artist: str | None) -> str:
    raw = f"{album or ''}\x1f{album_artist or ''}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _artist_key(album_artist: str | None) -> str:
    return hashlib.sha1((album_artist or "").encode("utf-8")).hexdigest()[:16]


def _track_dict(row) -> dict:
    return {k: row[k] for k in row.keys()}


async def list_folders(request: Request) -> JSONResponse:
    """?path=<đường dẫn tuyệt đối> -> thư mục con + track nằm trực tiếp
    trong đó. Không truyền path -> trả về các thư mục gốc (root)."""
    db = request.app.state.db
    path = request.query_params.get("path")

    if path is None:
        folders = db.query("SELECT * FROM folders WHERE is_root = 1 ORDER BY name")
        return JSONResponse({"folders": [dict(f) for f in folders], "tracks": []})

    folder_row = db.query_one("SELECT * FROM folders WHERE path = ?", (path,))
    if folder_row is None:
        return JSONResponse({"error": "folder_not_found"}, status_code=404)

    subfolders = db.query("SELECT * FROM folders WHERE parent_id = ? ORDER BY name", (folder_row["id"],))
    tracks = db.query(
        "SELECT * FROM tracks WHERE folder_id = ? ORDER BY disc_no, track_no, title",
        (folder_row["id"],),
    )
    return JSONResponse({
        "folder": dict(folder_row),
        "folders": [dict(f) for f in subfolders],
        "tracks": [_track_dict(t) for t in tracks],
    })


async def list_albums(request: Request) -> JSONResponse:
    db = request.app.state.db
    rows = db.query(
        """SELECT album, album_artist, COUNT(*) AS track_count, MIN(year) AS year
           FROM tracks WHERE album IS NOT NULL
           GROUP BY album, album_artist ORDER BY album_artist, year, album"""
    )
    albums = [
        {
            "album_key": _album_key(r["album"], r["album_artist"]),
            "album": r["album"],
            "album_artist": r["album_artist"],
            "track_count": r["track_count"],
            "year": r["year"],
        }
        for r in rows
    ]
    return JSONResponse({"albums": albums})


async def get_album_tracks(request: Request) -> JSONResponse:
    db = request.app.state.db
    album_key = request.path_params["album_key"]
    rows = db.query("SELECT DISTINCT album, album_artist FROM tracks WHERE album IS NOT NULL")
    match = next((r for r in rows if _album_key(r["album"], r["album_artist"]) == album_key), None)
    if match is None:
        return JSONResponse({"error": "album_not_found"}, status_code=404)
    tracks = db.query(
        "SELECT * FROM tracks WHERE album = ? AND (album_artist = ? OR (album_artist IS NULL AND ? IS NULL)) "
        "ORDER BY disc_no, track_no, title",
        (match["album"], match["album_artist"], match["album_artist"]),
    )
    return JSONResponse({
        "album": match["album"], "album_artist": match["album_artist"],
        "tracks": [_track_dict(t) for t in tracks],
    })


async def list_artists(request: Request) -> JSONResponse:
    db = request.app.state.db
    rows = db.query(
        """SELECT album_artist, COUNT(DISTINCT album) AS album_count, COUNT(*) AS track_count
           FROM tracks WHERE album_artist IS NOT NULL
           GROUP BY album_artist ORDER BY album_artist"""
    )
    artists = [
        {
            "artist_key": _artist_key(r["album_artist"]),
            "name": r["album_artist"],
            "album_count": r["album_count"],
            "track_count": r["track_count"],
        }
        for r in rows
    ]
    return JSONResponse({"artists": artists})


async def get_track(request: Request) -> JSONResponse:
    db = request.app.state.db
    track_id = request.path_params["track_id"]
    row = db.query_one("SELECT * FROM tracks WHERE id = ?", (track_id,))
    if row is None:
        return JSONResponse({"error": "track_not_found"}, status_code=404)
    return JSONResponse(_track_dict(row))


async def search(request: Request) -> JSONResponse:
    db = request.app.state.db
    q = request.query_params.get("q", "").strip()
    if not q:
        return JSONResponse({"tracks": [], "albums": [], "artists": []})
    like = f"%{q}%"
    tracks = db.query(
        "SELECT * FROM tracks WHERE title LIKE ? OR artist LIKE ? OR album LIKE ? LIMIT 50",
        (like, like, like),
    )
    albums_rows = db.query(
        "SELECT DISTINCT album, album_artist FROM tracks WHERE album LIKE ? LIMIT 50", (like,)
    )
    artists_rows = db.query(
        "SELECT DISTINCT album_artist FROM tracks WHERE album_artist LIKE ? LIMIT 50", (like,)
    )
    return JSONResponse({
        "tracks": [_track_dict(t) for t in tracks],
        "albums": [{"album_key": _album_key(r["album"], r["album_artist"]), "album": r["album"],
                     "album_artist": r["album_artist"]} for r in albums_rows],
        "artists": [{"artist_key": _artist_key(r["album_artist"]), "name": r["album_artist"]}
                    for r in artists_rows],
    })


async def trigger_scan(request: Request) -> JSONResponse:
    """Quét lại toàn bộ thư viện — dùng khi mới thêm thư mục NAS (Phần 5)
    hoặc thêm nhạc thủ công. Chạy trong thread pool vì scanner gọi ffprobe
    (blocking) rất nhiều lần."""
    import asyncio
    scanner = request.app.state.scanner
    config = request.app.state.config
    stats = await asyncio.to_thread(scanner.full_scan, config.library_roots)
    return JSONResponse({"status": "ok", "stats": stats})


async def list_roots(request: Request) -> JSONResponse:
    config = request.app.state.config
    return JSONResponse({
        "library_roots": [
            {"path": p, "exists": Path(p).exists()} for p in config.library_roots
        ]
    })


async def add_root(request: Request) -> JSONResponse:
    """Thêm 1 thư mục thư viện qua web — dùng cho lần thiết lập đầu tiên sau
    khi cài từ ISO (Phần "Cài đặt kiểu ROCK"), không cần SSH sửa config.json
    tay. Quét ngay + bắt đầu theo dõi realtime cho thư mục vừa thêm."""
    import asyncio
    config = request.app.state.config
    body = await request.json()
    raw_path = (body.get("path") or "").strip()
    if not raw_path:
        return JSONResponse({"error": "missing_path"}, status_code=400)
    normalized = str(Path(raw_path).expanduser().resolve())
    if not Path(normalized).is_dir():
        return JSONResponse({"error": "path_not_found",
                              "message": f"Không thấy thư mục '{normalized}' trên máy này."}, status_code=400)
    if normalized in config.library_roots:
        return JSONResponse({"status": "already_added", "library_roots": config.library_roots})

    config.library_roots.append(normalized)
    config.save()

    scanner = request.app.state.scanner
    stats = await asyncio.to_thread(scanner.full_scan, [normalized])

    watcher = request.app.state.watcher
    if watcher is not None:
        watcher.add_root(normalized)

    return JSONResponse({"status": "ok", "library_roots": config.library_roots, "scan_stats": stats})


async def remove_root(request: Request) -> JSONResponse:
    config = request.app.state.config
    body = await request.json()
    raw_path = (body.get("path") or "").strip()
    normalized = str(Path(raw_path).expanduser().resolve()) if raw_path else ""
    if normalized not in config.library_roots:
        return JSONResponse({"error": "not_found"}, status_code=404)

    config.library_roots.remove(normalized)
    config.save()

    watcher = request.app.state.watcher
    if watcher is not None:
        watcher.remove_root(normalized)

    return JSONResponse({"status": "ok", "library_roots": config.library_roots,
                          "note": "Nhạc đã quét trước đó vẫn còn trong DB; gọi lại /library/scan nếu muốn dọn track mồ côi."})
