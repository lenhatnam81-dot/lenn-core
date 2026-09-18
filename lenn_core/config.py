"""Cấu hình LENN Core.

Đọc từ file JSON (mặc định config.json ở thư mục gốc project, hoặc đường dẫn
truyền qua biến môi trường LENN_CORE_CONFIG). Nếu không có file, dùng giá trị
mặc định hợp lý để chạy thử ngay (thư viện rỗng, DB tại ./data/lenn_core.db).

Thiết kế để sau này (Phase 1+) mở rộng thêm nhiều zone, nhiều provider
streaming (Tidal/Qobuz) mà không phải đổi cấu trúc file config, chỉ thêm khóa.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(os.environ.get("LENN_CORE_CONFIG", "config.json"))

AUDIO_EXTENSIONS = {
    ".flac", ".wav", ".aiff", ".aif",
    ".mp3", ".m4a", ".aac", ".ogg", ".opus",
    ".dsf", ".dff",  # DSD
    ".ape", ".wv",
}


@dataclass
class ZoneConfig:
    id: str
    name: str
    # "alsa" (thiết bị DAC thật qua ALSA) | "file" (ghi ra wav, dùng để dev/test
    # khi máy không có audio hardware) | "null" (giải mã nhưng bỏ output).
    output_backend: str = "auto"
    alsa_device: str = "default"


@dataclass
class LennCoreConfig:
    library_roots: list[str] = field(default_factory=list)
    db_path: str = "data/lenn_core.db"
    artwork_cache_dir: str = "data/artwork"
    zones: list[ZoneConfig] = field(default_factory=lambda: [ZoneConfig(id="main", name="Main Zone")])
    http_host: str = "0.0.0.0"
    http_port: int = 8000
    scan_on_startup: bool = True
    watch_realtime: bool = True

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> "LennCoreConfig":
        path = Path(path)
        if not path.exists():
            cfg = cls()
            cfg._config_path = str(path)  # type: ignore[attr-defined]
            return cfg
        raw = json.loads(path.read_text(encoding="utf-8"))
        zones_raw = raw.get("zones") or [{"id": "main", "name": "Main Zone"}]
        zones = [ZoneConfig(**z) for z in zones_raw]
        cfg = cls(
            library_roots=raw.get("library_roots", []),
            db_path=raw.get("db_path", "data/lenn_core.db"),
            artwork_cache_dir=raw.get("artwork_cache_dir", "data/artwork"),
            zones=zones,
            http_host=raw.get("http_host", "0.0.0.0"),
            http_port=raw.get("http_port", 8000),
            scan_on_startup=raw.get("scan_on_startup", True),
            watch_realtime=raw.get("watch_realtime", True),
        )
        cfg._config_path = str(path)  # type: ignore[attr-defined]
        return cfg

    def to_json_dict(self) -> dict:
        return {
            "library_roots": self.library_roots,
            "db_path": self.db_path,
            "artwork_cache_dir": self.artwork_cache_dir,
            "zones": [
                {"id": z.id, "name": z.name, "output_backend": z.output_backend, "alsa_device": z.alsa_device}
                for z in self.zones
            ],
            "http_host": self.http_host,
            "http_port": self.http_port,
            "scan_on_startup": self.scan_on_startup,
            "watch_realtime": self.watch_realtime,
        }

    def save(self, path: str | None = None) -> None:
        """Ghi lại config.json — dùng khi người dùng thêm/xoá thư mục thư
        viện qua trang web (tab Cài đặt) thay vì phải SSH sửa tay, đúng tinh
        thần "không cần đăng nhập" cho việc dùng hàng ngày lẫn thiết lập ban
        đầu sau khi cài từ ISO."""
        target = Path(path or getattr(self, "_config_path", None) or DEFAULT_CONFIG_PATH)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_json_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        self._config_path = str(target)  # type: ignore[attr-defined]
