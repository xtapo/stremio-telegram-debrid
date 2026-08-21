# 📺 Film4k Live TV & Sports Addon Guide

Tài liệu hướng dẫn chi tiết về Addon **Film4k Live TV** (`film4k.net/tv`) - Nguồn phát hơn **200+ kênh truyền hình Việt Nam, Quốc Tế và các sự kiện thể thao trực tiếp** chất lượng cao Full HD / HD tích hợp sẵn cho **Stremio** và hỗ trợ xuất **IPTV M3U Playlist** cho mọi ứng dụng IPTV (TiviMate, VLC, OTT Navigator, Kodi...).

---

## 🌟 Tính Năng Nổi Bật

- 📡 **200+ Kênh Truyền Hình Đa Dạng**:
  - **K+ Truyền Hình**: K+ Sport 1, K+ Sport 2, K+ Cine, K+ Action, K+ Kids...
  - **VTV**: VTV1 HD - VTV9 HD, VTV5 các vùng miền (Tây Nam Bộ, Tây Nguyên...).
  - **HTV / HTVC**: HTV7 HD, HTV9 HD, HTV Thể Thao, Thuần Việt, Phim HD...
  - **Kênh Thể Thao**: FPT Sport, On Sport, Bóng đá, Tennis, Golf, NBA...
  - **Kênh Phim Điện Ảnh & Quốc Tế**: HBO, Cinemax, Warner TV, CinemaWorld, AXN...
  - **Kênh Thiếu Nhi & Hoạt Hình**: Cartoon Network, Cartoonito, Dreamworks, Bibi...
  - **Khoa Học & Khám Phá**: Discovery, Animal Planet, TLC, Nat Geo, Travel Living...
  - **Tin Tức & Thời Sự**: CNN, BBC, NHK World, DW, CNA, France 24, TV5, Quốc Hội...
  - **63 Kênh Đài Địa Phương**: THVL1 - THVL4 (Vĩnh Long), Hà Nội TV, Đà Nẵng, Hải Phòng, Cần Thơ, Bình Dương, Đồng Nai...
- ⚽ **Sự Kiện Thể Thao Trực Tiếp (Live Events)**:
  - Tự động cập nhật các trận đấu Ngoại Hạng Anh, Cúp C1, LPL, V-League, Tennis, eSports...
- 🚀 **Stream HLS Tốc Độ Cao & Ổn Định**:
  - Phát trực tiếp qua CDN HLS AVC/AAC không giật lag.
  - Hỗ trợ endpoint Dynamic Stream Redirector `/film4k/live/{id}.m3u8` tự động gia hạn token chữ ký CDN.
- 📥 **Hỗ Trợ M3U Playlist Cho IPTV Player**:
  - Xuất file hoặc link M3U đầy đủ `tvg-id`, `tvg-name`, `tvg-logo`, `group-title` dùng ngay trên Smart TV, Box Android, TiviMate, VLC, Kodi.
- 💻 **Trình Xem Web Live TV Tích Hợp (`/film4k/tv`)**:
  - Giao diện Dark Mode cao cấp, tích hợp HLS.js, thanh tìm kiếm kênh và phân loại danh mục thông minh.

---

## 🔗 Đường Dẫn Manifest & Cài Đặt Vào Stremio

Để cài đặt addon Film4k TV vào Stremio, bạn copy đường dẫn tương ứng bên dưới và dán vào thanh tìm kiếm **Addons** trên Stremio:

| Môi Trường | Đường Dẫn Stremio Manifest |
| :--- | :--- |
| **Localhost (Máy tính chạy server)** | `http://127.0.0.1:7860/film4k/manifest.json` |
| **Mạng Nội Bộ (LAN - Android TV, Phone, iPad)** | `http://<IP_LAN_CUA_BAN>:7860/film4k/manifest.json` |
| **Domain Public (Nếu có cấu hình)** | `https://your-domain.com/film4k/manifest.json` |

---

## 📥 Link IPTV M3U Playlist (Dành Cho TiviMate, VLC, OTT Navigator)

Bạn có thể dán link M3U Playlist sau vào các ứng dụng IPTV chuyên dụng:

```text
http://<IP_LAN_HOAC_DOMAIN>:7860/film4k/playlist.m3u
```

- **TiviMate / OTT Navigator**: Thêm Playlist mới -> Chọn M3U Playlist -> Dán URL trên.
- **VLC Media Player**: `Media` -> `Open Network Stream` (Ctrl + N) -> Dán URL playlist hoặc link kênh `.m3u8`.
- **Trình duyệt Web**: Truy cập `http://<IP_LAN_HOAC_DOMAIN>:7860/film4k/tv` để xem trực tiếp.

---

## ⚙️ Cấu Hình Môi Trường (.env)

Các thông số cấu hình Film4k trong file `.env`:

```env
# ==================================================================
# FILM4K LIVE TV (film4k.net/tv) - 200+ Kênh Truyền Hình & Sự Kiện Trực Tiếp
# ==================================================================
# Bật/Tắt nguồn Film4k Live TV (Mặc định: True)
ENABLE_SOURCE_FILM4K_TV=True

# Bật/Tắt hiển thị danh mục Film4k trên Trang chủ (Board) của Stremio (Mặc định: True)
ENABLE_BOARD_FILM4K_TV=True

# Tên miền Film4k (Mặc định: https://film4k.net)
FILM4K_BASE_URL=https://film4k.net

# Cookie phiên đăng nhập Film4k (session=...) dùng để xác thực lấy link luồng phát HLS
FILM4K_COOKIE=session=eyJhbGciOiJIUzI1NiJ9...
```

---

## 🔑 Hướng Dẫn Cập Nhật Cookie Khi Hết Hạn

Cookie phiên làm việc `session=...` có thời hạn khoảng 30 ngày. Khi cookie hết hạn, bạn có thể lấy cookie mới như sau:

1. Mở trình duyệt và truy cập [Film4k.net/tv](https://film4k.net/tv).
2. Đăng nhập tài khoản của bạn (Google, Email hoặc Telegram).
3. Bấm phím **F12** (hoặc chuột phải chọn *Inspect / Kiểm tra*) -> Chọn tab **Application / Ứng dụng** -> Chọn mục **Cookies** (`https://film4k.net`).
4. Tìm cookie có tên `session`, copy toàn bộ giá trị (`session=eyJhbGciOi...`).
5. Dán vào mục **Settings** trên Dashboard (`/dashboard`) hoặc cập nhật biến `FILM4K_COOKIE` trong file `.env`.

---

## 📡 Danh Sách API Endpoints Của Film4k Addon

- `GET /film4k/manifest.json`: Manifest Addon Stremio.
- `GET /film4k/catalog/tv/film4k_tv_channels.json`: Danh sách 200+ kênh truyền hình (hỗ trợ lọc thể loại `genre=...`).
- `GET /film4k/catalog/tv/film4k_tv_events.json`: Danh sách các sự kiện & trận đấu thể thao trực tiếp.
- `GET /film4k/meta/tv/{id}.json`: Chi tiết kênh và sự kiện (logo, poster, mô tả).
- `GET /film4k/stream/tv/{id}.json`: Phân giải luồng phát trực tiếp HLS `.m3u8`.
- `GET /film4k/live/{id}.m3u8`: Redirect 302 đến link HLS signed CDN mới nhất (dùng cho M3U).
- `GET /film4k/playlist.m3u`: Xuất danh sách phát chuẩn M3U cho IPTV player.
- `GET /film4k/tv` (hoặc `/film4k/player`): Trình xem TV trực tiếp trên nền tảng Web.
- `GET /film4k/status`: Kiểm tra trạng thái kết nối & số lượng kênh Film4k.
