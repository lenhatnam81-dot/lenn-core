#!/usr/bin/env bash
# Dựng file ISO cài đặt LENN Core kiểu Roon ROCK: cắm USB, bật máy, cài xong
# tự khởi động lại vào LENN Core đang chạy — không cần gõ gì trong lúc cài.
#
# QUAN TRỌNG — chạy script này trên MỘT MÁY UBUNTU/DEBIAN BÌNH THƯỜNG CÓ
# INTERNET (máy dev của bạn, không phải máy chủ nhạc, và không phải trong
# sandbox này) — sandbox tạo mã nguồn ở đây không có quyền tải ISO
# Ubuntu/cài xorriso, nên bản thân file .iso phải được dựng ở nơi khác.
# Việc build này chỉ cần làm 1 lần (hoặc mỗi khi ra bản LENN Core mới), rồi
# dùng lại file .iso đó để cài cho mọi máy Beast/Phoenix/Rogue.
#
# Cách dùng:
#   ./build-iso.sh --repo git@github.com:lennaudio/lenn-core.git \
#                   --ssh-pubkey ~/.ssh/id_ed25519.pub \
#                   --output lenn-core-rock.iso
#
# Xem README.md cùng thư mục để biết đầy đủ điều kiện tiên quyết + cách
# test trong máy ảo trước khi flash ra USB thật.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$(mktemp -d /tmp/lenn-iso-build.XXXXXX)"
GENERATOR_DIR="${WORK_DIR}/ubuntu-autoinstall-generator"
GENERATOR_REPO="https://github.com/covertsh/ubuntu-autoinstall-generator.git"

HOSTNAME_="lenn-core"
ADMIN_USER="lenn"
ADMIN_PASSWORD=""
SSH_PUBKEY_FILE=""
HTTP_PORT="8000"
UBUNTU_RELEASE_FLAG="-r"   # dùng bản release ổn định thay vì daily build
OUTPUT="lenn-core-rock.iso"
LENN_CORE_REPO=""
declare -a LIBRARY_PATHS=()
SOURCE_ISO=""

usage() {
  cat <<EOF
Cách dùng: $0 --repo <git-url-mã-nguồn-lenn-core> [tuỳ chọn khác]

Bắt buộc:
  --repo <url>            Git repo chứa mã nguồn LENN Core (đã push zip lên
                           trước, xem README.md cùng thư mục này)

Tuỳ chọn:
  --hostname <tên>        Mặc định: lenn-core
  --admin-user <tên>      Tài khoản quản trị hệ điều hành (KHÔNG phải tài
                           khoản để dùng LENN Core — LENN Core không có
                           đăng nhập). Mặc định: lenn
  --admin-password <mk>   Mật khẩu tài khoản trên. Không truyền -> tự sinh
                           ngẫu nhiên và in ra MỘT LẦN lúc build, hãy lưu lại.
  --ssh-pubkey <file>      Public key để chỉ cho đăng nhập SSH bằng khoá,
                           tắt luôn đăng nhập SSH bằng mật khẩu (khuyến nghị).
  --port <số>              Cổng HTTP của LENN Core. Mặc định: 8000
  --library <path>         Thư mục nhạc thêm sẵn (có thể lặp lại nhiều lần).
                           Có thể bỏ qua và thêm sau qua trang web (tab Cài đặt).
  --iso <file.iso>         Dùng file ISO Ubuntu Server đã tải sẵn thay vì để
                           script tự tải bản release mới nhất.
  --output <file.iso>      Tên file ISO kết quả. Mặc định: lenn-core-rock.iso
  -h, --help               Hiện hướng dẫn này
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) LENN_CORE_REPO="$2"; shift 2 ;;
    --hostname) HOSTNAME_="$2"; shift 2 ;;
    --admin-user) ADMIN_USER="$2"; shift 2 ;;
    --admin-password) ADMIN_PASSWORD="$2"; shift 2 ;;
    --ssh-pubkey) SSH_PUBKEY_FILE="$2"; shift 2 ;;
    --port) HTTP_PORT="$2"; shift 2 ;;
    --library) LIBRARY_PATHS+=("$2"); shift 2 ;;
    --iso) SOURCE_ISO="$2"; shift 2 ;;
    --output) OUTPUT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Tham số không rõ: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "${LENN_CORE_REPO}" ]]; then
  echo "LỖI: thiếu --repo <git-url>. Đây là nơi late-commands sẽ git clone mã nguồn LENN Core vào máy đích lúc cài." >&2
  echo "     Đẩy source code (zip đã nhận) lên một git repo (GitHub riêng tư, hoặc git server nội bộ của LENN) rồi truyền URL đó vào đây." >&2
  exit 1
fi

echo "==> Kiểm tra/cài công cụ cần thiết trên máy build này (cần sudo + internet)..."
MISSING=()
for bin in xorriso curl gpg git openssl; do
  command -v "$bin" >/dev/null 2>&1 || MISSING+=("$bin")
done
if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "    Cài: ${MISSING[*]}"
  sudo apt-get update -y
  sudo apt-get install -y xorriso curl gnupg git openssl isolinux p7zip-full
fi

echo "==> Tải bộ công cụ dựng ISO (ubuntu-autoinstall-generator)..."
git clone --depth 1 "${GENERATOR_REPO}" "${GENERATOR_DIR}"

echo "==> Chuẩn bị mật khẩu quản trị hệ điều hành..."
if [[ -z "${ADMIN_PASSWORD}" ]]; then
  ADMIN_PASSWORD="$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | head -c 20)"
  echo "    Không truyền --admin-password -> đã tự sinh mật khẩu ngẫu nhiên:"
  echo ""
  echo "    >>> Tài khoản quản trị OS: ${ADMIN_USER} / mật khẩu: ${ADMIN_PASSWORD} <<<"
  echo "    (LƯU LẠI NGAY — chỉ in ra một lần, dùng để SSH vào máy khi cần bảo trì."
  echo "     KHÔNG liên quan đến việc dùng LENN Core hàng ngày — web LENN Core không cần đăng nhập.)"
  echo ""
fi
ADMIN_PASSWORD_HASH="$(openssl passwd -6 "${ADMIN_PASSWORD}")"

SSH_ALLOW_PW="true"
SSH_PUBKEY_RAW=""
if [[ -n "${SSH_PUBKEY_FILE}" ]]; then
  [[ -f "${SSH_PUBKEY_FILE}" ]] || { echo "LỖI: không thấy file --ssh-pubkey ${SSH_PUBKEY_FILE}" >&2; exit 1; }
  SSH_ALLOW_PW="false"
  SSH_PUBKEY_RAW="$(cat "${SSH_PUBKEY_FILE}")"
  echo "==> Dùng SSH key từ ${SSH_PUBKEY_FILE}, tắt đăng nhập SSH bằng mật khẩu."
fi

echo "==> Sinh cấu hình autoinstall (user-data) từ template..."
RENDERED_USER_DATA="${WORK_DIR}/user-data"
# Truyền toàn bộ giá trị động qua argv (không nhúng vào mã nguồn Python) để
# tránh vỡ cú pháp nếu mật khẩu/khoá SSH có chứa dấu ngoặc kép, backslash...
RENDER_ARGS=(
  "${SCRIPT_DIR}/user-data.template" "${RENDERED_USER_DATA}"
  --hostname "${HOSTNAME_}"
  --admin-user "${ADMIN_USER}"
  --admin-password-hash "${ADMIN_PASSWORD_HASH}"
  --ssh-allow-pw "${SSH_ALLOW_PW}"
  --ssh-pubkey "${SSH_PUBKEY_RAW}"
  --repo-url "${LENN_CORE_REPO}"
  --http-port "${HTTP_PORT}"
)
for lib in "${LIBRARY_PATHS[@]:-}"; do
  [[ -z "$lib" ]] && continue
  RENDER_ARGS+=(--library "$lib")
done
python3 "${SCRIPT_DIR}/render_user_data.py" "${RENDER_ARGS[@]}"

echo "==> Dựng ISO (tải Ubuntu Server ISO nếu chưa có sẵn, có thể mất vài phút)..."
GEN_ARGS=(-a -u "${RENDERED_USER_DATA}" -m "${SCRIPT_DIR}/meta-data" -d "${OUTPUT}" "${UBUNTU_RELEASE_FLAG}")
if [[ -n "${SOURCE_ISO}" ]]; then
  GEN_ARGS+=(-s "${SOURCE_ISO}")
fi
bash "${GENERATOR_DIR}/generate.sh" "${GEN_ARGS[@]}"

sha256sum "${OUTPUT}" | tee "${OUTPUT}.sha256"

echo ""
echo "=================================================================="
echo " Xong: ${OUTPUT}"
echo ""
echo " Bước tiếp theo:"
echo " 1. TEST TRƯỚC trong máy ảo (VirtualBox/QEMU/VMware) — boot thử ISO"
echo "    này, xác nhận cài tự động chạy hết, khởi động lại vào LENN Core,"
echo "    mở được http://<ip-máy-ảo>:${HTTP_PORT}/ — trước khi đụng vào máy thật."
echo " 2. Flash ra USB bằng Rufus (Windows) hoặc balenaEtcher (Mac/Linux)."
echo "    Dòng lệnh (cẩn thận đúng /dev/sdX, sai là mất dữ liệu):"
echo "      sudo dd if=${OUTPUT} of=/dev/sdX bs=4M status=progress conv=fsync"
echo " 3. Cắm USB vào Beast/Phoenix/Rogue, bật máy, chọn boot từ USB."
echo "    CẢNH BÁO: cài đặt sẽ XOÁ SẠCH ổ đĩa đầu tiên của máy đó."
echo " 4. Sau khi máy tự khởi động lại xong (không cần thao tác gì), mở"
echo "    trình duyệt tới http://<ip-máy>:${HTTP_PORT}/ — dùng ngay, không đăng nhập."
echo "=================================================================="

rm -rf "${WORK_DIR}"
