# Dựng ISO cài LENN Core kiểu Roon ROCK

Mục tiêu: một file `.iso` mà bạn flash ra USB (Rufus/balenaEtcher/`dd`), cắm
vào Beast/Phoenix/Rogue, bật máy, chọn boot từ USB — máy tự cài hệ điều
hành + LENN Core, tự khởi động lại, xong là dùng được ngay qua trình duyệt,
**không cần gõ gì trong suốt quá trình cài, không cần đăng nhập gì để
dùng**. Đúng tinh thần Roon ROCK.

## Vì sao phải chạy ở máy khác, không phải trong phiên làm việc với Claude này

File `.iso` là một bản dựng nhị phân của cả một hệ điều hành — để tạo ra nó
cần tải ISO Ubuntu Server gốc (~2GB) và các công cụ dựng ISO
(`xorriso`, `isolinux`...). Môi trường sandbox mà Claude chạy để viết code
này **bị chặn theo chính sách mạng** tới cả kho gói Ubuntu/Debian lẫn trang
tải ISO chính thức, và cũng không có sẵn `xorriso`/`isolinux` để cài thêm.
Đây không phải giới hạn có thể "vòng qua" được — nên phần dựng ISO thật sự
phải chạy trên một máy Ubuntu/Debian bình thường của bạn, có internet.
Việc này chỉ cần làm 1 lần (hoặc mỗi khi cập nhật LENN Core), rồi dùng lại
file `.iso` đó cho mọi máy Beast/Phoenix/Rogue sau này.

Toàn bộ phần "trí tuệ" của bộ cài — `packaging/install.sh`,
`packaging/lenn-core.service`, cấu hình autoinstall — đã được chuẩn bị sẵn
ở đây; máy build chỉ đóng gói lại thành `.iso`, không cần tự viết gì thêm.

## Điều kiện tiên quyết

1. Một máy Ubuntu hoặc Debian bình thường, có internet, có quyền `sudo`.
2. Mã nguồn LENN Core đã được đẩy lên một **git repo** bạn kiểm soát (GitHub
   riêng tư, GitLab/Gitea nội bộ, v.v.) — vì lúc cài, máy đích sẽ tự
   `git clone` mã nguồn từ đó về. Nếu bạn chưa có, cách nhanh nhất:
   ```bash
   unzip lenn-core-phase0.zip -d .
   cd lenn-core
   git init && git add -A && git commit -m "LENN Core Phase 0"
   git remote add origin git@github.com:<ten-to-chuc>/lenn-core.git
   git push -u origin main
   ```
3. (Khuyến nghị) một cặp khoá SSH để đăng nhập bảo trì máy sau này thay vì
   dùng mật khẩu: `ssh-keygen -t ed25519 -f ~/.ssh/lenn_core_admin`.

## Chạy

```bash
cd packaging/iso-builder
./build-iso.sh \
  --repo git@github.com:<ten-to-chuc>/lenn-core.git \
  --ssh-pubkey ~/.ssh/lenn_core_admin.pub \
  --output lenn-core-rock.iso
```

Script sẽ tự cài `xorriso`/`isolinux`/... nếu máy build chưa có, tự tải bộ
công cụ `ubuntu-autoinstall-generator` (dự án mã nguồn mở được cộng đồng
dùng rộng rãi để chính xác việc này — tự tay viết lại phần "khoét" ISO bằng
`xorriso` là việc dễ vỡ theo từng phiên bản Ubuntu, nên tận dụng công cụ đã
được kiểm chứng thay vì làm lại), tự tải ISO Ubuntu Server bản ổn định mới
nhất, rồi nhúng cấu hình autoinstall vào.

Nếu không truyền `--admin-password`, script tự sinh một mật khẩu ngẫu nhiên
cho tài khoản quản trị hệ điều hành và **chỉ in ra một lần** — lưu lại ngay.
Tài khoản này chỉ để SSH vào bảo trì máy khi cần, hoàn toàn tách biệt với
việc dùng LENN Core hàng ngày (không có đăng nhập).

Xem toàn bộ tham số: `./build-iso.sh --help`.

## Bắt buộc: test trong máy ảo trước khi đụng vào máy thật

Vì phần dựng ISO không thể chạy thử/boot thử trong sandbox lúc viết code
này, **tuyệt đối nên** boot thử file `.iso` vừa tạo trong máy ảo trước:

```bash
# VirtualBox
VBoxManage createvm --name lenn-core-test --register
VBoxManage createhd --filename lenn-core-test.vdi --size 20000
# ... gắn ổ đĩa + gắn lenn-core-rock.iso làm ổ CD, khởi động máy ảo
```

hoặc nhanh hơn với QEMU (nếu máy build có sẵn):

```bash
qemu-img create -f qcow2 disk.qcow2 20G
qemu-system-x86_64 -m 4096 -enable-kvm -boot d \
  -cdrom lenn-core-rock.iso -drive file=disk.qcow2,format=qcow2
```

Xác nhận: máy ảo tự cài xong không hỏi gì, tự khởi động lại, và
`http://<ip-máy-ảo>:8000/` mở được trang LENN Core — rồi mới flash ra USB
thật và cắm vào Beast/Phoenix/Rogue.

## Flash ra USB & cài lên máy thật

```bash
# Windows: dùng Rufus, chọn file .iso, chọn đúng USB, ghi.
# macOS/Linux: dùng balenaEtcher (giao diện), hoặc dòng lệnh:
sudo dd if=lenn-core-rock.iso of=/dev/sdX bs=4M status=progress conv=fsync
```

**Cảnh báo quan trọng, giống hệt cảnh báo của bộ cài Roon ROCK:** quá trình
cài đặt sẽ **xoá sạch ổ đĩa đầu tiên** của máy đích (`storage.layout.name:
direct` trong `user-data.template`) — đây là máy chuyên dụng làm music
server, không phải máy dùng chung việc khác.

Sau khi cắm USB, bật máy, chọn boot từ USB trong BIOS/UEFI — còn lại tự
động hết: cài hệ điều hành, tải và cài LENN Core, khởi động lại. Xong, mở
`http://<ip-máy>:8000/` — dùng ngay.

## Cập nhật LENN Core sau này

Vì mã nguồn được `git clone` lúc cài (không đóng cứng vào ISO), nâng cấp
không cần dựng lại ISO: SSH vào máy bằng tài khoản quản trị, sau đó

```bash
cd /opt/lenn-core-src && git pull && sudo ./packaging/install.sh --port 8000
```

(`install.sh` chạy lại an toàn — cập nhật code/venv rồi khởi động lại
service, không đụng tới dữ liệu thư viện/DB đã có ở `/var/lib/lenn-core`).

## Các tệp trong thư mục này

```
build-iso.sh            script chính, chạy trên máy build có internet
render_user_data.py     điền giá trị (hostname, mật khẩu, khoá SSH...) vào template một cách an toàn
user-data.template       cấu hình autoinstall (mẫu, có placeholder)
meta-data                 file nocloud bắt buộc, gần như rỗng
```
