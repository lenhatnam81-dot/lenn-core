#!/usr/bin/env bash
# Gỡ LENN Core khỏi máy. Mặc định giữ lại dữ liệu (DB, artwork) ở
# /var/lib/lenn-core và cấu hình ở /etc/lenn-core — thêm --purge để xoá luôn.
set -euo pipefail

SERVICE_NAME="lenn-core"
APP_DIR="/opt/lenn-core"
DATA_DIR="/var/lib/lenn-core"
CONF_DIR="/etc/lenn-core"
PURGE=0

[[ "${1:-}" == "--purge" ]] && PURGE=1

if [[ $EUID -ne 0 ]]; then
  echo "Cần chạy bằng root (sudo)." >&2
  exit 1
fi

systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload

rm -rf "${APP_DIR}"

if [[ "${PURGE}" -eq 1 ]]; then
  rm -rf "${DATA_DIR}" "${CONF_DIR}"
  userdel lenncore 2>/dev/null || true
  echo "Đã gỡ hoàn toàn LENN Core, kể cả dữ liệu và cấu hình."
else
  echo "Đã gỡ LENN Core. Dữ liệu (${DATA_DIR}) và cấu hình (${CONF_DIR}) vẫn giữ nguyên."
  echo "Chạy lại với --purge nếu muốn xoá luôn."
fi
