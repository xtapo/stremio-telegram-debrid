# 🌐 Hướng Dẫn Kênh Truyền Hình IPTV Theo Quốc Gia (IPTV-Org)

Addon **IPTV Org - Kênh TV Chia Theo Quốc Gia** tích hợp kho dữ liệu luồng phát truyền hình trực tiếp công khai lớn nhất thế giới từ [iptv-org/iptv](https://github.com/iptv-org/iptv), hỗ trợ hơn **200+ quốc gia & vùng lãnh thổ** với hàng ngàn kênh TV chất lượng cao hoàn toàn miễn phí.

---

## 🌟 Tính Năng Nổi Bật

- 🌍 **200+ Quốc Gia Toàn Cầu**: Việt Nam 🇻🇳, Mỹ 🇺🇸, Anh 🇬🇧, Nhật Bản 🇯🇵, Hàn Quốc 🇰🇷, Pháp 🇫🇷, Đức 🇩🇪, Trung Quốc 🇨🇳, Thái Lan 🇹🇭, Singapore 🇸🇬, Canada 🇨🇦, Úc 🇦🇺, Tây Ban Nha 🇪🇸, Ý 🇮🇹, Nga 🇷🇺, v.v.
- ⚡ **Luồng Phát Trực Tiếp M3U8/HLS Tốc Độ Cao**: Tương thích hoàn hảo với ứng dụng Stremio và mọi trình duyệt web hiện đại.
- 🗂️ **Phân Loại & Lọc Thể Loại**: News (Tin tức), Sports (Thể thao), Movies & Cinema (Phim ảnh), Entertainment (Giải trí), Kids (Thiếu nhi), Science & Discovery (Khoa học khám phá), Music (Âm nhạc).
- 📱 **Giao Diện Web TV Player Cao Cấp**: Trình phát Dark Mode Glassmorphism tại `/iptv/tv` với bộ chuyển đổi quốc gia nhanh, thanh tìm kiếm thông minh, và hỗ trợ phát toàn màn hình.
- 🚀 **Bộ Nhớ Đệm Đa Tầng (Multi-Layer Cache)**: Phản hồi 0ms với bộ nhớ đệm tự động cập nhật liên tục từ GitHub.

---

## 🔗 Đường Dẫn Cài Đặt Stremio Addon

Sau khi khởi chạy ứng dụng, bạn có thể cài đặt addon vào Stremio bằng các đường dẫn sau:

| Môi Trường | Đường Dẫn Manifest Stremio |
| :--- | :--- |
| **Localhost (Máy tính hiện tại)** | `http://127.0.0.1:7860/iptv/manifest.json` |
| **Mạng Nội Bộ (LAN - TV, Phone, iPad)** | `http://<IP_LAN_CỦA_BẠN>:7860/iptv/manifest.json` |
| **Domain Public (Nếu có cấu hình)** | `https://<YOUR_DOMAIN>/iptv/manifest.json` |

> 💡 **Mẹo:** Bạn có thể mở trực tiếp đường dẫn `stremio://127.0.0.1:7860/iptv/manifest.json` trong trình duyệt để Stremio tự động mở và cài đặt 1-Click!

---

## 📺 Xem Trực Tiếp Trên Web TV Player

Nếu không dùng Stremio, bạn có thể xem trực tiếp qua trình duyệt web:

- **Web TV Player**: [http://127.0.0.1:7860/iptv/tv](http://127.0.0.1:7860/iptv/tv) (hoặc `/iptv` / `/iptv/player`)
- **Chọn Quốc Gia Nhanh**: Nhấp vào biểu tượng lá cờ (🇻🇳, 🇺🇸, 🇬🇧, 🇯🇵, 🇰🇷, ...) hoặc chọn từ danh sách 200+ quốc gia trong menu thả xuống.
- **Tìm Kiếm**: Nhập tên kênh vào ô tìm kiếm để lọc kênh ngay tức thì.

---

## ⚙️ Cấu Hình Môi Trường (.env)

Bạn có thể tùy chỉnh các tham số trong file `.env`:

```env
# Bật/Tắt nguồn kênh TV IPTV Org (Mặc định: True)
ENABLE_SOURCE_IPTV=True

# Bật/Tắt hiển thị trên Bảng khám phá / Trang chủ Stremio (Mặc định: True)
ENABLE_BOARD_IPTV=True
```

---

## 📑 Danh Sách API Endpoints

- `GET /iptv/manifest.json`: Manifest chuẩn Stremio Protocol.
- `GET /iptv/catalog/tv/iptv_channels.json`: Danh sách kênh mặc định (Việt Nam).
- `GET /iptv/catalog/tv/iptv_channels/genre={Country}.json`: Danh sách kênh theo quốc gia được chọn.
- `GET /iptv/meta/tv/{id}.json`: Chi tiết metadata kênh truyền hình.
- `GET /iptv/stream/tv/{id}.json`: Luồng phát trực tiếp của kênh.
- `GET /iptv/api/countries`: Danh sách 200+ quốc gia kèm mã ISO và cờ.
- `GET /iptv/api/channels?country={code}`: Danh sách kênh theo mã quốc gia (vn, us, jp, fr, ...).
- `GET /iptv/tv`: Giao diện Web TV Player.
