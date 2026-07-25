# 🔞 TopXX Cinema - Stremio Addon (HLS HD Trực Tiếp)

Hệ thống Addon TopXX cho phép khám phá, tìm kiếm và xem phim 18+ Vietsub chất lượng cao HD/Full HD trực tiếp trên Trình phát mặc định của Stremio (LibVLC / ExoPlayer) thông qua nguồn API `https://topxx.vip/api`.

---

## ✨ Tính năng nổi bật của TopXX Addon

1. **Phát Trực Tiếp HLS trên Stremio**:
   - Sử dụng đường truyền `.m3u8` trực tiếp từ máy chủ phát (`embed.streamxx.net`).
   - Tự động cung cấp các tùy chọn phát: **⚡ HLS Direct**, **▶ Proxy Server**, và **🌐 Web Player**.
   - Tương thích tốt trên **Stremio Desktop (Windows/Mac), Android, iOS và Smart TV / Android TV**.

2. **Bộ lọc Khám Phá (Discover) Đa dạng**:
   - **Phim Đăng Hôm Nay (Today)**: Danh sách phim được đăng mới trong ngày từ endpoint `/movies/today`.
   - **Phim Mới Cập Nhật (Latest)**: Danh sách tất cả phim mới nhất từ endpoint `/movies/latest`.
   - **Phim Theo Thể Loại**: Việt Sub, Hentai 18+, Không che, Tập thể, Âu Mỹ, Xnxx, Chubby, Vú to, Sex Less, Sex Nga, Amateur...
   - **Phim Theo Quốc Gia**: Việt Nam, Nhật Bản, Mỹ, Trung Quốc, Tây Ban Nha, Nga...

3. **Tìm Kiếm Phim Trực Tiếp**:
   - Hỗ trợ công cụ tìm kiếm của Stremio theo tên phim hoặc từ khóa.

---

## 🚀 Hướng dẫn Khởi động & Cài đặt vào Stremio

### 1. Khởi động Máy chủ Addon

Trong cửa sổ Terminal / PowerShell tại thư mục dự án, chạy lệnh khởi động:

```powershell
python nguonc_router.py
```
*(Máy chủ sẽ khởi động trên cổng `7071` tích hợp cả TopXX Addon, VSMov Addon và NguonC Addon).*

---

### 2. Đường dẫn Cài đặt Manifest URL (Stremio)

Tùy theo môi trường chạy của bạn:

* **Xem trên cùng máy tính (Stremio Desktop App):**
  ```text
  http://127.0.0.1:7071/topxx/manifest.json
  ```

* **Xem từ thiết bị khác trong mạng LAN (Điện thoại, Smart TV, Tablet...):**
  ```text
  http://<IP_LAN_CỦA_MÁY_TÍNH>:7071/topxx/manifest.json
  ```
  *(Ví dụ: `http://192.168.1.100:7071/topxx/manifest.json` - Đảm bảo đã chạy file `add_firewall_rule.bat` bằng quyền Administrator để mở cổng `7071` qua Windows Firewall).*

* **Xem trên Stremio Web (`web.stremio.com`):**
  - Khởi tạo HTTPS Tunnel qua Localtunnel hoặc Cloudflare Tunnel.
  - Dán đường dẫn Manifest HTTPS vào Stremio:
    ```text
    https://<your-domain>/topxx/manifest.json
    ```

---

### 3. Các bước thêm Addon vào ứng dụng Stremio

1. Mở ứng dụng **Stremio**.
2. Nhấp vào mục **Addons** (biểu tượng mảnh ghép) ➔ Chọn **Add Addon** hoặc **Paste Addon URL**.
3. Dán đường dẫn Manifest URL ở trên vào và nhấn **Install**.
4. Chuyển sang danh mục **Discover (Khám phá)** ➔ Chọn **TopXX - Phim 18+ Vietsub** để thưởng thức!

---

## 🛠️ Danh sách Endpoints API của TopXX Addon

| Endpoint | Mô tả |
| :--- | :--- |
| `GET /topxx/manifest.json` | Khai báo Manifest Addon theo chuẩn Stremio Protocol |
| `GET /topxx/catalog/movie/topxx_phim_moi.json` | Lấy danh sách phim mới nhất |
| `GET /topxx/catalog/movie/topxx_the_loai/genre={genre}.json` | Lọc danh sách phim theo Thể loại |
| `GET /topxx/catalog/movie/topxx_quoc_gia/genre={country}.json` | Lọc danh sách phim theo Quốc gia |
| `GET /topxx/catalog/movie/topxx_phim_moi/search={keyword}.json` | Tìm kiếm phim theo từ khóa |
| `GET /topxx/meta/movie/topxx:{code}.json` | Lấy chi tiết thông tin phim & hình ảnh |
| `GET /topxx/stream/movie/topxx:{code}.json` | Trích xuất link phát HLS (.m3u8), Proxy và Embed Player |
| `GET /topxx/stream_proxy` | Stream Proxy nội bộ tối ưu luồng HLS |
