# 🌐 Hướng Dẫn Kênh Truyền Hình Trực Tuyến Toàn Cầu TVRun (tvrun.online)

Addon **TVRun - Free Global Live TV Streaming** tích hợp kho truyền hình trực tiếp công khai phong phú từ [TVRun](https://tvrun.online/), tổng hợp đa nguồn bao gồm hơn **200+ quốc gia & vùng lãnh thổ**, **Free-TV Global (2.000+ kênh)**, **YouTube Live Streams**, và các kênh chất lượng cao độc quyền hoàn toàn miễn phí.

---

## 🌟 Tính Năng Nổi Bật

- 🌍 **200+ Quốc Gia & Vùng Lãnh Thổ**: Việt Nam 🇻🇳, Mỹ 🇺🇸, Anh 🇬🇧, Nhật Bản 🇯🇵, Hàn Quốc 🇰🇷, Pháp 🇫🇷, Đức 🇩🇪, Trung Quốc 🇨🇳, Thái Lan 🇹🇭, Singapore 🇸🇬, Canada 🇨🇦, Úc 🇦🇺, Tây Ban Nha 🇪🇸, Ý 🇮🇹, Ấn Độ 🇮🇳, v.v.
- 🌐 **Free-TV Global**: Hơn 2.000+ kênh truyền hình quốc tế chọn lọc.
- 🔴 **YouTube Live Streams**: Kênh tin tức & truyền hình phát sóng trực tiếp qua YouTube Live M3U.
- ⭐ **TVRun Verified**: Kênh độc quyền được tuyển chọn (như TvOasis).
- ⚡ **Luồng Phát Trực Tiếp M3U8/HLS Tốc Độ Cao**: Tương thích hoàn hảo với ứng dụng Stremio và mọi trình duyệt web hiện đại.
- 🗂️ **Phân Loại & Lọc Thể Loại**: News (Tin tức), Sports (Thể thao), Movies & Cinema (Phim ảnh), Entertainment (Giải trí), Kids (Thiếu nhi), Science & Discovery (Khoa học khám phá), Music (Âm nhạc).
- 📱 **Giao Diện Web TV Player Cao Cấp**: Trình phát Dark Mode Glassmorphism tại `/tvrun/tv` với bộ chuyển đổi quốc gia nhanh, thanh tìm kiếm thông minh, nút sao chép link stream và hỗ trợ phát toàn màn hình.
- 📥 **Xuất Playlist M3U**: Hỗ trợ xuất danh sách kênh định dạng `.m3u` tại `/tvrun/playlist.m3u` cho các ứng dụng IPTV chuyên dụng (VLC, TiviMate, OTT Navigator, Kodi).
- 🚀 **Bộ Nhớ Đệm Đa Tầng (Multi-Layer Cache)**: Phản hồi 0ms với bộ nhớ đệm tự động cập nhật liên tục.

---

## 🔗 Đường Dẫn Cài Đặt Stremio Addon

Sau khi khởi chạy ứng dụng, bạn có thể cài đặt addon vào Stremio bằng các đường dẫn sau:

| Môi Trường | Đường Dẫn Manifest Stremio |
| :--- | :--- |
| **Localhost (Máy tính hiện tại)** | `http://127.0.0.1:7860/tvrun/manifest.json` |
| **Mạng Nội Bộ (LAN - TV, Phone, iPad)** | `http://<IP_LAN_CỦA_BẠN>:7860/tvrun/manifest.json` |
| **Domain Public (Nếu có cấu hình)** | `https://<YOUR_DOMAIN>/tvrun/manifest.json` |

> 💡 **Mẹo:** Bạn có thể mở trực tiếp đường dẫn `stremio://127.0.0.1:7860/tvrun/manifest.json` trong trình duyệt để Stremio tự động mở và cài đặt 1-Click!

---

## 📺 Xem Trực Tiếp Trên Web TV Player

Nếu không dùng Stremio, bạn có thể xem trực tiếp qua trình duyệt web:

- **Web TV Player**: [http://127.0.0.1:7860/tvrun/tv](http://127.0.0.1:7860/tvrun/tv) (hoặc `/tvrun` / `/tvrun/player`)
- **Chọn Nhanh Quốc Gia & Nguồn**: Nhấp vào biểu tượng lá cờ (🇻🇳, 🇺🇸, 🇬🇧, 🇯🇵, 🇰🇷, 🌐 Free-TV, 🔴 YouTube Live, ⭐ Verified) hoặc chọn từ danh sách 200+ quốc gia trong menu thả xuống.
- **Tìm Kiếm**: Nhập tên kênh vào ô tìm kiếm để lọc kênh ngay tức thì.
- **Tải Playlist M3U**: Nhấp nút **Tải M3U** hoặc truy cập `http://127.0.0.1:7860/tvrun/playlist.m3u`.

---

## ⚙️ Cấu Hình Môi Trường (.env)

Bạn có thể tùy chỉnh các tham số trong file `.env`:

```env
# Bật/Tắt nguồn kênh TV TVRun Global (Mặc định: True)
ENABLE_SOURCE_TVRUN=True

# Bật/Tắt hiển thị trên Bảng khám phá / Trang chủ Stremio (Mặc định: True)
ENABLE_BOARD_TVRUN=True

# Base URL của TVRun
TVRUN_BASE_URL=https://tvrun.online
```

---

## 📑 Danh Sách API Endpoints

- `GET /tvrun/manifest.json`: Manifest chuẩn Stremio Protocol.
- `GET /tvrun/catalog/tv/tvrun_channels.json`: Danh sách kênh mặc định (Việt Nam).
- `GET /tvrun/catalog/tv/tvrun_channels/genre={GenreOrCountry}.json`: Danh sách kênh theo quốc gia/thể loại được chọn.
- `GET /tvrun/meta/tv/{id}.json`: Chi tiết metadata kênh truyền hình.
- `GET /tvrun/stream/tv/{id}.json`: Luồng phát trực tiếp của kênh.
- `GET /tvrun/playlist.m3u`: Xuất danh sách phát M3U cho VLC / TiviMate.
- `GET /tvrun/api/countries`: Danh sách 200+ quốc gia kèm mã ISO, cờ và các nguồn đặc biệt.
- `GET /tvrun/api/channels?source={code}`: Danh sách kênh theo nguồn (vn, us, freetv, youtube, featured, ...).
- `GET /tvrun/tv`: Giao diện Web TV Player Dark Mode Glassmorphism.
