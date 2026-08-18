# ✨ Ernax Player Addon Guide

Tài liệu hướng dẫn chi tiết về Addon **Ernax Player** (`ernax.pro`) - Kho phim chiếu rạp, phim lẻ & series truyền hình quốc tế chất lượng siêu cao (4K UHD 2160p / 1080p Full HD / 720p HD) tích hợp sẵn trên Stremio Hub.

---

## 🌟 Tính Năng Nổi Bật

- 🚀 **Giải mã Python thuần tốc độ cao (< 1ms)**: Tự động trích xuất và giải mã luồng phát mã hóa từ hệ thống CDN của Ernax mà không cần cài NodeJS hoặc chạy trình duyệt ngoài.
- ⚡ **HLS Master Adaptive Bitrate**:
  - **Master Playlist Auto**: Tự động nhận diện và chuyển đổi độ phân giải mượt mà (4K 2160p, 1080p, 720p, 480p) theo tốc độ mạng.
  - **Từng luồng phân giải riêng biệt**: 2160p (4K UHD), 1080p (Full HD), 720p (HD), 480p (SD).
- 🌐 **Web Embed Player trực tiếp**: Cho phép bấm mở phát trực tiếp trên giao diện web của `ernax.pro` (tiêu tốn 0% băng thông máy chủ).
- 💬 **Phụ đề Đa Ngôn Ngữ**: Tự động trích xuất danh sách phụ đề VTT đa quốc gia từ CDN của Ernax và cung cấp qua endpoint phụ đề chuẩn Stremio.
- 🎯 **Hỗ trợ Metadata TMDB & IMDb toàn diện**:
  - Hiển thị đầy đủ poster, backdrop gốc 4K, tóm tắt nội dung, năm phát hành, diễn viên, điểm số IMDb/TMDB.
  - Hỗ trợ đầy đủ các mùa (Seasons) và tập phim (Episodes) đối với Phim Bộ (TV Series).
- 🔍 **Tìm kiếm & Phân loại thể loại**:
  - Tìm kiếm nhanh chóng cả phim lẻ và phim bộ theo tên tiếng Anh / Quốc tế.
  - Bộ lọc 18+ thể loại: Hành động, Viễn tưởng, Hoạt hình, Kinh dị, Hài hước, Bí ẩn...
- 🎛️ **Quản lý Dashboard tiện lợi**: Bật/tắt nguồn và cài đặt trực tiếp vào ứng dụng Stremio trên PC, TV, Android, iOS.

---

## 🔗 Đường Dẫn Manifest & Cài Đặt Vào Stremio

Để thêm addon vào Stremio, bạn sao chép đường dẫn tương ứng bên dưới và dán vào thanh tìm kiếm **Addons** trên Stremio:

| Môi Trường | Đường Dẫn Manifest Addon |
| :--- | :--- |
| **Localhost (Máy chủ chạy addon)** | `http://127.0.0.1:7860/ernax/manifest.json` |
| **Mạng Nội Bộ (LAN - TV, Phone, iPad)** | `http://<IP_LAN_CUA_BAN>:7860/ernax/manifest.json` |
| **Domain Public (Nếu có cấu hình)** | `https://your-domain.com/ernax/manifest.json` |

---

## ⚙️ Cấu Hình Môi Trường (.env)

Bạn có thể tùy chỉnh các thông số của Ernax Player trong file `.env`:

```env
# ==================================================================
# ERNAX PLAYER (ernax.pro) - Kho Phim & TV Series 4K UHD / 1080p
# ==================================================================
# Bật/Tắt nguồn Ernax Player (Mặc định: True)
ENABLE_SOURCE_ERNAX=True

# Bật/Tắt hiển thị danh mục Ernax trên Trang chủ (Board) của Stremio (Mặc định: True)
ENABLE_BOARD_ERNAX=True
```

---

## 📡 API Endpoints Của Ernax Addon

- `GET /ernax/manifest.json`: Trả về thông tin manifest addon Stremio.
- `GET /ernax/catalog/{type}/{id}.json`: Danh mục phim phổ biến, top rated, trending, tìm kiếm, lọc thể loại.
- `GET /ernax/meta/{type}/{id}.json`: Chi tiết phim / TV series (hỗ trợ định dạng `ernax:...`, `tmdb:...`, `tt...`).
- `GET /ernax/stream/{type}/{id}.json`: Lấy danh sách link phát HLS Master, 4K, 1080p, 720p và link Web Embed.
- `GET /ernax/subtitles/{type}/{id}.json`: Lấy danh sách phụ đề trích xuất trực tiếp từ CDN.
- `GET /ernax/stream_proxy`: Proxy HLS Playlist và video chunks bypass CORS & Referer mượt mà.
