# 👑 Vidking Player Addon Guide

Tài liệu hướng dẫn chi tiết về Addon **Vidking Player** (`vidking.net`) - Kho phim chiếu rạp, phim lẻ & series truyền hình quốc tế chất lượng cao (4K UHD / 1080p Full HD) tích hợp sẵn trên Stremio.

---

## 🌟 Tính Năng Nổi Bật

- 🚀 **Giải mã Python thuần tốc độ cao**: Không phụ thuộc NodeJS hay Browser bên ngoài, tốc độ phân giải stream < 1ms.
- 📺 **Đa dạng Server Stream**:
  - **Yoru**: HLS Stream Master M3U8 đa độ phân giải (2160p 4K, 1080p FHD, 720p HD, 480p).
  - **Cypher**: Direct MP4 chất lượng cao.
  - **Neon, Vyse, Breach, Omen, Raze**: Hệ thống server dự phòng phong phú.
- 🎯 **Hỗ trợ toàn diện Metadata TMDB & IMDb**:
  - Tự động lấy poster, backdrop 4K, diễn viên, điểm đánh giá IMDb, ngày phát hành.
  - Hỗ trợ đầy đủ các mùa (Seasons) và danh sách tập (Episodes) kèm thumbnail và ngày phát sóng.
- 🔍 **Tìm kiếm & Bộ lọc thể loại thông minh**:
  - Tìm kiếm phim lẻ & series nhanh chóng qua mirror API.
  - Lọc theo 18+ thể loại (Hành động, Phiêu lưu, Hoạt hình, Kinh dị, Viễn tưởng...).
- 🎛️ **Quản lý Dashboard 1-Click**: Bật/tắt nguồn và cài đặt trực tiếp vào ứng dụng Stremio trên điện thoại, TV, PC.

---

## 🔗 Đường Dẫn Manifest & Cài Đặt Vào Stremio

Để thêm addon vào Stremio, bạn copy đường dẫn tương ứng bên dưới và dán vào thanh tìm kiếm **Addons** trên Stremio:

| Môi Trường | Đường Dẫn Manifest Addon |
| :--- | :--- |
| **Localhost (Máy chủ chạy addon)** | `http://127.0.0.1:7860/vidking/manifest.json` |
| **Mạng Nội Bộ (LAN - TV, Phone, iPad)** | `http://<IP_LAN_CUA_BAN>:7860/vidking/manifest.json` |
| **Domain Public (Nếu có cấu hình)** | `https://your-domain.com/vidking/manifest.json` |

---

## ⚙️ Cấu Hình Môi Trường (.env)

Bạn có thể tùy chỉnh các thông số của Vidking trong file `.env`:

```env
# ==================================================================
# VIDKING PLAYER (vidking.net) - Kho Phim & TV Series 4K / 1080p
# ==================================================================
# Bật/Tắt nguồn Vidking Player (Mặc định: True)
ENABLE_SOURCE_VIDKING=True

# Bật/Tắt hiển thị danh mục Vidking trên Trang chủ (Board) của Stremio (Mặc định: True)
ENABLE_BOARD_VIDKING=True
```

---

## 📡 API Endpoints Của Vidking Addon

- `GET /vidking/manifest.json`: Trả về thông tin manifest addon Stremio.
- `GET /vidking/catalog/{type}/{id}.json`: Danh mục phim phổ biến, top rated, trending.
- `GET /vidking/meta/{type}/{id}.json`: Chi tiết phim / TV series (hỗ trợ `vidking:...`, `tmdb:...`, `tt...`).
- `GET /vidking/stream/{type}/{id}.json`: Lấy danh sách link phát HLS & MP4 theo các chất lượng.
