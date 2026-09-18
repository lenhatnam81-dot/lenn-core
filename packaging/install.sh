#!/usr/bin/env bash
# Bộ cài LENN Core cho máy chủ âm nhạc (Beast/Phoenix/Rogue) — kiểu ROCK:
# cài xong chạy nền, tự khởi động cùng máy, KHÔNG cần đăng nhập/tài khoản
# gì để dùng — điều khiển hoàn toàn qua trang web nội bộ (không đăng nhập).
#
# Dùng cho Debian/Ubuntu (hoặc bản Linux tương thích apt) đã cài sẵn trên
# phần cứng LENN. Chạy với quyền root:
#
#   sudo ./install.sh --library /mnt/music --library /mnt/nas/music --port 8000
#
# Có thể chạy lại nhiều lần (idempotent) để cập nhật code/khi nâng cấp.

set -euo pipefail

APP_DIR="/opt/lenn-core"
DATA_DIR="/var/lib/lenn-core"
CONF_DIR="/etc/lenn-core"
CONF_FILE="${CONF_DIR}/config.json"
SERVICE_USER="lenncore"
SERVICE_NAME="lenn-core"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PORT=8000
declare -a LIBRARY_ROOTS=()
ZONE_NAME="Main Zone"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --library) LIBRARY_ROOTS+=("$2"); shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --zone-name) ZONE_NAME="$2"; shift 2 ;;
    *) echo "Tham số không rõ: $1" >&2; exit 1 ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "Cần chạy bằng root (sudo)." >&2
  exit 1
fi

echo "==> Cài gói hệ thống cần thiết (ffmpeg, python3-venv)..."
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y || echo "!! apt-get update lỗi (có thể do mạng) — tiếp tục, giả định gói đã có sẵn."
  apt-get install -y ffmpeg python3 python3-venv python3-pip \
    || echo "!! Không cài được qua apt — kiểm tra lại ffmpeg/python3 đã có sẵn chưa."
else
  echo "!! Không thấy apt-get — bỏ qua bước cài gói tự động, tự đảm bảo đã có ffmpeg + python3 + python3-venv."
fi

command -v ffmpeg >/dev/null 2>&1 || { echo "LỖI: thiếu ffmpeg, không thể tiếp tục." >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "LỖI: thiếu python3, không thể tiếp tục." >&2; exit 1; }

echo "==> Tạo user hệ thống '${SERVICE_USER}' (không có mật khẩu, không đăng nhập được — chỉ để chạy service)..."
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --home-dir "${APP_DIR}" --shell /usr/sbin/nologin --groups audio,plugdev "${SERVICE_USER}"
fi

echo "==> Sao chép mã nguồn vào ${APP_DIR} ..."
mkdir -p "${APP_DIR}"
rsync -a --delete \
  --exclude 'tests' --exclude '.git' --exclude '__pycache__' --exclude 'data' --exclude 'config.json' \
  "${SRC_DIR}/" "${APP_DIR}/" 2>/dev/null || cp -r "${SRC_DIR}/." "${APP_DIR}/"

echo "==> Tạo virtualenv & cài thư viện Python (cần máy có internet)..."
python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --upgrade pip
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

echo "==> Tạo thư mục dữ liệu ${DATA_DIR} ..."
mkdir -p "${DATA_DIR}/artwork" "${DATA_DIR}/zone_output"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}" "${DATA_DIR}"

echo "==> Ghi cấu hình ${CONF_FILE} ..."
mkdir -p "${CONF_DIR}"
if [[ ! -f "${CONF_FILE}" ]]; then
  python3 - "$CONF_FILE" "$PORT" "$ZONE_NAME" "${LIBRARY_ROOTS[@]}" <<'PYEOF'
import json, sys
conf_file, port, zone_name, *roots = sys.argv[1:]
config = {
    "library_roots": roots,
    "db_path": "/var/lib/lenn-core/lenn_core.db",
    "artwork_cache_dir": "/var/lib/lenn-core/artwork",
    "zones": [{"id": "main", "name": zone_name, "output_backend": "auto", "alsa_device": "default"}],
    "http_host": "0.0.0.0",
    "http_port": int(port),
    "scan_on_startup": True,
    "watch_realtime": True,
}
with open(conf_file, "w", encoding="utf-8") as f:
    json.dump(config, f, ensure_ascii=False, indent=2)
PYEOF
  echo "    Đã tạo config mới. Thư viện: ${LIBRARY_ROOTS[*]:-<chưa có, thêm sau trong ${CONF_FILE}>}"
else
  echo "    Đã có sẵn ${CONF_FILE} — giữ nguyên (xoá file này nếu muốn tạo lại từ đầu)."
fi

echo "==> Cài đặt systemd service ..."
cp "${SRC_DIR}/packaging/lenn-core.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  echo "==> Mở cổng ${PORT}/tcp trên ufw ..."
  ufw allow "${PORT}/tcp" || true
fi

IP_ADDR="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo ""
echo "=================================================================="
echo " LENN Core đã cài xong và đang chạy nền (systemctl status ${SERVICE_NAME})."
echo " Không cần đăng nhập/tài khoản gì cả — mở trình duyệt trong mạng LAN tới:"
echo ""
echo "   http://${IP_ADDR:-<ip-may-nay>}:${PORT}/"
echo ""
echo " Sửa thư viện nhạc / thêm NAS: sửa ${CONF_FILE} rồi 'systemctl restart ${SERVICE_NAME}'"
echo " Xem log: journalctl -u ${SERVICE_NAME} -f"
echo "=================================================================="
