# LENN Core — Phase 0 (MVP)

Bộ não trung tâm của phần mềm nghe nhạc LENN Audio Design, tương đương
**Roon Core**. Đây là bản hiện thực **Phase 0** theo lộ trình trong tài liệu
kiến trúc "Kiến trúc phần mềm nghe nhạc LENN (giống Roon)": thư viện nhạc
local (metadata + folder), audio engine 1 zone, REST API + SSE cho LENN
Remote và Display API.

## Đã làm được (khớp với 7 hạng mục bạn nêu)

| # | Hạng mục | Trạng thái trong bản này |
| - | -------- | ------------------------- |
| 1 | Roon Core | **Có** — LENN Core: quét thư viện, quản lý metadata, audio engine, API server; cài đặt kiểu appliance (systemd, không đăng nhập) + bộ dựng ISO flash-USB kiểu Roon ROCK (`packaging/iso-builder/`) |
| 2 | Hệ máy con dùng RAAT | Kiến trúc Zone/ZoneManager đã tách lớp sẵn (`zones.py`), Phase 0 chạy 1 zone ngay trên Core; **chưa** làm giao thức mạng LAT/Snapcast thật cho zone ở máy khác (đúng lộ trình: việc này thuộc Phase 1) |
| 3 | Tidal, Qobuz | **Chưa** — cần xin quyền đối tác trước (xem tài liệu kiến trúc, Phần 3); code đã chừa sẵn chỗ để thêm Provider module |
| 4 | Thư viện theo folder kiểu JRiver | **Có** — `GET /library/folders`, index cây thư mục thật song song với index metadata |
| 5 | Kết nối thư viện NAS | **Có về nguyên lý** — chỉ cần mount SMB/NFS ở tầng OS rồi thêm đường dẫn vào `library_roots`; scanner/watcher không phân biệt local hay NAS mount (xem mục "Thư viện trên NAS" bên dưới) |
| 6 | Điều khiển qua điện thoại | REST API đầy đủ cho remote (play/pause/seek/volume/queue) + tự động phát hiện Core qua UDP broadcast + **trang web điều khiển tối giản** (`web/index.html`, không đăng nhập) để dùng tạm/kiểm tra; **chưa** viết app Flutter thật |
| 7 | Hiển thị màn hình qua API | **Có** — `GET /zones/{id}/now-playing` + `GET /events` (SSE) đẩy real-time |

## Cài đặt kiểu ROCK lên phần cứng sản phẩm (Beast/Phoenix/Rogue)

Đúng như bạn dặn: đây là phần mềm cài đặt **local trên Linux của chính máy
chủ**, không phải dịch vụ đám mây — giống triết lý Roon ROCK (Roon Optimized
Core Kit): cài một lần, chạy nền vĩnh viễn, tự khởi động cùng máy.

**Không có đăng nhập / tài khoản nào cả.** Vì LENN Core chỉ cài trên máy của
chính LENN Audio Design (không phải dịch vụ nhiều người dùng như Roon phải
gắn với tài khoản Roon để đồng bộ), toàn bộ hệ thống không có màn hình đăng
nhập, không có user/password — mở trình duyệt trong mạng LAN nội bộ là dùng
được ngay. Mô hình tin cậy là theo mạng: ai vào được mạng LAN/Wi-Fi của bạn
thì điều khiển được máy; nếu cần chặt hơn, giới hạn ở tường lửa/router chứ
không phải ở tầng ứng dụng.

### Cách 1 — Flash USB kiểu Roon ROCK (khuyến nghị cho sản phẩm thật)

Đây là cách giống hệt trải nghiệm Roon ROCK mà bạn yêu cầu: dựng sẵn 1 file
`.iso`, flash ra USB, cắm vào Beast/Phoenix/Rogue, bật máy chọn boot từ USB
— máy **tự cài hết, không hỏi gì, không cần gõ lệnh**, xong tự khởi động
lại và dùng được ngay qua trình duyệt.

Bộ công cụ dựng ISO nằm ở `packaging/iso-builder/` — xem
[`packaging/iso-builder/README.md`](packaging/iso-builder/README.md) để có
hướng dẫn đầy đủ. Tóm tắt quy trình:

1. Trên **một máy Ubuntu/Debian khác có internet** (không phải máy đích),
   chạy `packaging/iso-builder/build-iso.sh --repo <git-repo-của-bạn> ...`
   để tạo ra file `lenn-core-rock.iso`. *(Lý do phải làm ở máy khác: việc
   dựng ISO cần tải ~2GB ISO Ubuntu gốc và công cụ `xorriso`/`isolinux` từ
   kho Ubuntu — môi trường sandbox dùng để viết bộ code này bị chính sách
   mạng nội bộ chặn truy cập các kho đó nên không tự dựng được ISO tại đây;
   đây không phải giới hạn kỹ thuật của LENN Core, chỉ là giới hạn của môi
   trường viết code, và chỉ cần làm bước này 1 lần.)*
2. **Bắt buộc** boot thử file `.iso` trong máy ảo (VirtualBox/QEMU) trước
   khi đụng vào máy thật — script và README đều nói rõ cách làm.
3. Flash ra USB (Rufus / balenaEtcher / `dd`), cắm vào máy đích, bật máy,
   chọn boot từ USB. Còn lại tự động: cài OS, cài LENN Core, khởi động lại.
   **Cảnh báo: quá trình này xoá sạch ổ đĩa đầu tiên của máy đích**, giống
   hệt cảnh báo của Roon ROCK — chỉ dùng cho máy chuyên dụng làm music
   server.
4. Mở `http://<ip-máy>:8000/` — dùng ngay, không cần đăng nhập. Nếu máy vừa
   cài xong chưa có thư viện nhạc nào, dùng ngay mục "Cài đặt" trong trang
   web để trỏ tới thư mục nhạc (xem "Thêm thư viện lần đầu qua web" bên
   dưới) — **không cần SSH vào máy sửa file cấu hình tay**.

### Cách 2 — Cài trực tiếp bằng script (khi máy đích đã có sẵn Ubuntu/Debian)

Trên máy đã có sẵn Debian/Ubuntu Server (khuyến nghị headless, không cài môi
trường desktop — giống ROCK), chạy với quyền root:

```bash
sudo ./packaging/install.sh \
  --library /mnt/music \
  --library /mnt/nas/music \
  --port 8000
```

Script sẽ: cài ffmpeg/python3 (qua apt, cần máy có internet lúc cài), tạo
user hệ thống riêng không đăng nhập được để chạy service, cài LENN Core vào
`/opt/lenn-core`, ghi cấu hình vào `/etc/lenn-core/config.json`, cài đặt và
bật `systemd` service `lenn-core` (tự khởi động cùng máy, tự restart nếu
crash). Xong việc, chỉ cần mở `http://<ip-máy>:8000/` — có ngay trang điều
khiển web tối giản (duyệt thư viện, phát nhạc, điều khiển zone) mà không
cần cài thêm gì, dùng để kiểm tra máy chạy đúng ngay sau khi cài, và làm nền
tham khảo cho app LENN Remote (Flutter) sau này.

Gỡ cài đặt: `sudo ./packaging/uninstall.sh` (thêm `--purge` để xoá luôn dữ
liệu/cấu hình).

Chạy dev/test nhanh không qua installer, xem mục "Cài đặt & chạy" bên dưới.

### Thêm thư viện lần đầu qua web (không cần SSH)

Cả hai cách cài trên đều khởi động LENN Core với thư viện **rỗng** (đúng
trạng thái máy vừa cài xong từ ISO). Vì yêu cầu "không cần đăng nhập/tài
khoản gì để dùng" cũng có nghĩa là không nên bắt bạn phải SSH vào sửa
`config.json` bằng tay chỉ để trỏ thư mục nhạc lần đầu, trang web điều
khiển có sẵn 2 API để làm việc này ngay từ trình duyệt:

```
POST   /library/roots   {"path": "/mnt/music"}   # thêm 1 thư mục, quét ngay + theo dõi realtime luôn, không cần khởi động lại service
DELETE /library/roots   {"path": "/mnt/music"}   # bỏ theo dõi 1 thư mục (nhạc đã quét vẫn còn trong DB tới khi quét lại)
GET    /library/roots                             # xem danh sách thư mục hiện tại + còn tồn tại trên đĩa hay không
```

Thư mục thêm qua đây được ghi lại vào `config.json` trên đĩa ngay lập tức,
nên khởi động lại máy/service vẫn nhớ. Nếu nhạc nằm trên NAS, mount NAS vào
hệ điều hành trước (xem mục "Thư viện trên NAS" bên dưới) rồi mới `POST` đường
dẫn đã mount vào đây.

### Cấu hình PC đề xuất (tham khảo theo Roon ROCK/Nucleus)

Roon công bố mức tối thiểu **CPU Intel Core i3 (Ivy Bridge trở lên), RAM
4GB, ổ boot SSD**; bản ROCK chính thức (cài qua image USB, chỉ chạy trên
NUC được chứng nhận) khuyến nghị cụ thể hơn theo quy mô thư viện. LENN Core
nhẹ hơn Roon (không có nhận diện giọng nói, DSP phòng, hay xử lý ảnh bìa
độ phân giải cực cao), nên các mức dưới đây là đủ dư, không cần bám sát tối
đa:

| Quy mô | CPU | RAM | Ổ đĩa | Mạng |
| --- | --- | --- | --- | --- |
| Thư viện nhỏ/vừa (< 12.000 album), 1-2 zone | Core i3 / N100 trở lên (x86_64) | 4GB | SSD 64-128GB cho OS (tách riêng khỏi ổ chứa nhạc) | Ethernet có dây khuyến nghị hơn Wi-Fi |
| Thư viện lớn (12.000+ album) hoặc nhiều zone cùng lúc | Core i5/i7 trở lên | 8GB (Roon ghi nhận trên 8GB gần như không tận dụng thêm — LENN Core cũng vậy) | SSD 128-256GB cho OS + ổ riêng (HDD/SSD nội bộ, USB, hoặc NAS) cho nhạc | Ethernet có dây, Gigabit nếu stream nhiều zone hi-res đồng thời |

Ghi chú quan trọng (đúng khuyến nghị Roon ROCK): **luôn tách ổ chứa hệ điều
hành/LENN Core khỏi ổ chứa nhạc** — dù nhạc để ở ổ nội bộ thứ hai, USB rời,
hay NAS qua SMB/NFS (Phần 5) đều được, chỉ cần thêm đường dẫn vào
`library_roots`.

## Vì sao không đúng 100% tech stack đã đề xuất trong tài liệu kiến trúc

Môi trường build bản này (sandbox) **không có quyền tải gói mới từ PyPI hay
apt** (chính sách mạng chặn pypi.org/archive.ubuntu.com). Vì vậy một vài lựa
chọn kỹ thuật được thay thế bằng thứ đã sẵn có, không đổi hành vi/API:

- **Metadata**: dùng `ffprobe` (có sẵn cùng ffmpeg) thay vì `mutagen`. Đọc
  tag tốt cho FLAC/ALAC/WAV/DSD/MP3/AAC/OGG — không phải giải pháp yếu hơn,
  chỉ là thay thư viện.
- **Web framework**: dùng `Starlette` (nền của FastAPI, đã có sẵn) thay vì
  `FastAPI` trực tiếp. API surface tương đương.
- **Kênh real-time**: dùng **SSE** (`sse-starlette`, có sẵn) thay vì
  WebSocket, vì gói `websockets`/`wsproto` mà `uvicorn` cần để chạy WebSocket
  không cài được. SSE vẫn đẩy sự kiện real-time một chiều Core → client —
  đủ cho now-playing/trạng thái zone. Khi triển khai thật (máy có internet
  bình thường), có thể `pip install websockets` rồi bổ sung endpoint
  WebSocket song song mà không phải đổi kiến trúc.
- **Audio engine**: dùng `ffmpeg` subprocess (không phải engine C++/Rust
  riêng như đề xuất dài hạn, cũng không phải `mpv` vì không cài được). Đây
  vốn dĩ là hướng hợp lý cho MVP; xem mục Giới hạn bên dưới.
- **Khám phá thiết bị (Phần 6)**: dùng UDP broadcast tự viết thay vì
  `zeroconf`/mDNS thật, vì `zeroconf` không cài được. Tương đương chức năng
  ở quy mô LAN gia đình.

Trên máy chủ Beast/Phoenix/Rogue thật (có internet bình thường), bạn hoàn
toàn có thể `pip install fastapi mutagen websockets zeroconf mpv` và nâng
cấp dần từng phần này mà không phải viết lại kiến trúc.

## Cài đặt & chạy (dev/test nhanh, không qua installer)

Dùng khi bạn đang phát triển/thử trên máy tính thường, không phải cài lên
sản phẩm thật (xem mục cài đặt kiểu ROCK ở trên cho việc đó):

```bash
pip install -r requirements.txt
cp config.example.json config.json   # rồi sửa library_roots, zones cho đúng máy bạn
python3 scripts/run.py --config config.json
```

Server mặc định chạy ở `http://0.0.0.0:8000` — mở bằng trình duyệt để thấy
ngay trang điều khiển web (không cần đăng nhập).

## Thư viện trên NAS (Phần 5)

1. Mount thư mục NAS ở tầng hệ điều hành trước, ví dụ:
   `mount -t cifs //nas-ip/Music /mnt/nas/music -o username=...,vers=3.0`
   (hoặc mount NFS tương tự — Synology/QNAP/TrueNAS đều hỗ trợ cả hai).
2. Thêm đường dẫn đã mount (`/mnt/nas/music`) vào `library_roots` trong
   `config.json`.
3. Khởi động lại LENN Core, hoặc gọi `POST /library/scan` nếu server đang
   chạy.

`watcher.py` sẽ theo dõi realtime các thư mục này, nhưng vì `inotify` không
phải lúc nào cũng ổn định 100% qua network mount, bạn nên đặt thêm việc gọi
`POST /library/scan` định kỳ (ví dụ cron mỗi giờ) làm lớp dự phòng, đúng như
lưu ý trong tài liệu kiến trúc.

## API chính

```
GET  /health
GET    /library/roots
POST   /library/roots  {path}              # thêm thư mục thư viện lúc đang chạy, không cần SSH (xem mục "Thêm thư viện lần đầu qua web")
DELETE /library/roots  {path}              # bỏ theo dõi 1 thư mục
GET  /library/folders?path=<path>          # Folder Browser kiểu JRiver
GET  /library/albums
GET  /library/albums/{album_key}/tracks
GET  /library/artists
GET  /library/tracks/{id}
GET  /library/search?q=...
POST /library/scan

GET  /zones
GET  /zones/{zone_id}
GET  /zones/{zone_id}/now-playing          # dùng cho Display API
POST /zones/{zone_id}/play      {track_id} hoặc {track_ids:[...], start_index}
POST /zones/{zone_id}/pause
POST /zones/{zone_id}/resume
POST /zones/{zone_id}/stop
POST /zones/{zone_id}/seek      {position_seconds}
POST /zones/{zone_id}/volume    {volume: 0-100}
POST /zones/{zone_id}/next
POST /zones/{zone_id}/previous
POST /zones/{zone_id}/queue     {track_ids:[...]}

GET  /events                                # SSE: now_playing_changed, playback_state_changed, queue_changed
```

## Giới hạn đã biết & hướng nâng cấp (đọc trước khi triển khai thật)

- **pause/resume** dùng `SIGSTOP`/`SIGCONT` trên tiến trình ffmpeg — hoạt
  động đúng nhưng không "mượt" bằng engine chuyên dụng.
- **seek() và set_volume()** phải khởi động lại tiến trình ffmpeg tại vị trí
  mới (ffmpeg không có kênh điều khiển realtime như mpv IPC) — gây gián đoạn
  rất ngắn. Khi nâng cấp engine (mpv hoặc LAT riêng theo Phase 3), đây là chỗ
  cần thay trước tiên.
- Backend `"alsa"` cần chạy trên máy có card âm thanh thật (Beast/Phoenix/
  Rogue). Môi trường không có `/proc/asound` sẽ tự chuyển sang backend
  `"file"` (ghi ra `.wav`) để vẫn kiểm chứng được toàn bộ pipeline.
- Multi-zone hiện tại là nhiều tiến trình ffmpeg độc lập trên cùng Core,
  **chưa đồng bộ mẫu (sample-accurate sync)** giữa các zone — đúng theo lộ
  trình, việc này thuộc Phase 1 (tích hợp Snapcast) / Phase 3 (LAT riêng).

## Test

Dùng `unittest` (thư viện chuẩn Python, không cần cài `pytest` — cũng vì lý
do môi trường build không tải được gói mới):

```bash
python3 -m unittest discover -s tests -v
```

23 test đã chạy qua trên bản này: quét thư viện (metadata + folder tree,
rescan không nhân đôi), API thư viện/tìm kiếm/folder browser, toàn bộ
vòng đời phát nhạc thật qua ffmpeg (play → pause → resume → stop, chuyển
bài tự động khi hết bài, next/previous, volume) — kiểm chứng bằng file
`.wav` thực sự được ghi ra, không phải mock — và thêm/xoá thư mục thư viện
qua web lúc đang chạy (`POST`/`DELETE /library/roots`), gồm cả xác nhận
watcher realtime tự gắn theo dõi cho thư mục vừa thêm mà không cần khởi
động lại service (đúng kịch bản máy vừa cài xong từ ISO).

## Cấu trúc code

```
lenn_core/
  config.py       cấu hình
  db.py           SQLite: bảng folders + tracks (2 chỉ mục song song)
  metadata.py     trích metadata bằng ffprobe
  scanner.py      quét thư viện (full scan + index từng file)
  watcher.py      theo dõi realtime bằng watchdog
  player.py       audio engine 1 zone (ffmpeg subprocess)
  zones.py        Zone + ZoneManager (queue, trạng thái, sự kiện)
  events.py       event bus nội bộ cho SSE
  discovery.py    tự phát hiện Core trong LAN qua UDP
  api/
    app.py            ghép toàn bộ thành ứng dụng Starlette (route "/" phục vụ web/index.html)
    library.py        route thư viện
    playback.py       route điều khiển phát nhạc
    events_routes.py  route SSE
web/index.html    trang điều khiển web tối giản, không đăng nhập (xem "Cài đặt kiểu ROCK")
packaging/
  install.sh          bộ cài kiểu ROCK: apt, venv, systemd, cấu hình
  uninstall.sh         gỡ cài đặt
  lenn-core.service    unit file systemd
  iso-builder/         dựng file .iso flash-USB kiểu Roon ROCK (chạy trên máy build riêng có internet — xem README trong thư mục này)
scripts/run.py    chạy server (dùng bởi cả dev lẫn install.sh/systemd)
tests/            unittest, sinh dữ liệu test bằng ffmpeg (tests/fixtures.py)
```

## Việc tiếp theo (Phase 1, theo tài liệu kiến trúc)

Nói tiếp trong tài liệu kiến trúc trên Claude Docs của bạn — gợi ý thứ tự:
tích hợp Snapcast cho multi-zone đồng bộ thật, khung Provider module cho
Tidal/Qobuz (song song với việc xin quyền đối tác), rồi app LENN Remote
(Flutter).
