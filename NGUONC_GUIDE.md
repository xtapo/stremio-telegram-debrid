# 🎬 NguonC Cinema - Stremio Addon

Addon tích hợp trực tiếp kho phim **Phim Lẻ, Phim Bộ, TV Shows, Hoạt Hình** từ **NguonC API** (`https://phim.nguonc.com/api-document`) vào ứng dụng **Stremio**.

---

## ✨ Tính năng nổi bật

- 📺 **Danh mục phong phú**: Phim Mới Cập Nhật, Phim Lẻ, Phim Bộ, Đang Chiếu, TV Shows.
- 🎭 **Bộ lọc Thể loại đầy đủ (22 thể loại)**: Hành Động, Phiêu Lưu, Hoạt Hình, Phim Hài, Hình Sự, Tài Liệu, Chính Kịch, Gia Đình, Giả Tưởng, Lịch Sử, Kinh Dị, Phim Nhạc, Bí Ẩn, Lãng Mạn, Khoa Học Viễn Tưởng, Gây Cấn, Chiến Tranh, Tâm Lý, Tình Cảm, Cổ Trang, Miền Tây, Phim 18+.
- 🌍 **Bộ lọc Quốc gia (16 quốc gia / khu vực)**: Âu Mỹ, Anh, Trung Quốc, Indonesia, Việt Nam, Pháp, Hồng Kông, Hàn Quốc, Nhật Bản, Thái Lan, Đài Loan, Nga, Hà Lan, Philippines, Ấn Độ, Quốc gia khác.
- 📅 **Bộ lọc Năm phát hành**: Lọc đầy đủ theo năm phát hành từ **2004 đến 2026**.
- 🔍 **Tìm kiếm trực tiếp**: Tìm kiếm bất kỳ phim nào từ thanh Search của Stremio.
- ⚡ **Tự động giải mã luồng HLS (.m3u8)**: Tự động trích xuất link phát trực tiếp HLS `.m3u8` sắc nét, phát native trong trình phát mặc định của Stremio (ExoPlayer/VLC).
- 🌐 **Fallback Web Embed Player**: Hỗ trợ link xem qua Trình duyệt Web nếu muốn dùng giao diện player gốc.

---

## 🚀 Hướng dẫn Khởi động & Cài đặt vào Stremio

### 1. Khởi động Máy chủ Addon

Trong cửa sổ Terminal (PowerShell), chạy lệnh khởi động máy chủ:

```powershell
python nguonc_router.py
```
*(Server chạy trên cổng `7071` tích hợp cả NguonC Addon lẫn VSMov Addon)*

---

### 2. Đường dẫn Cài đặt Manifest URL (Stremio)

Tùy vào thiết bị và môi trường của bạn:

* **Xem trên cùng máy tính (Stremio Desktop App):**
  ```text
  http://127.0.0.1:7071/nguonc/manifest.json
  ```
* **Xem từ thiết bị khác trong cùng mạng Wi-Fi/LAN (Điện thoại, Smart TV, Android TV, iPad...):**
  ```text
  http://<IP_LAN_CUA_MAY_TINH>:7071/nguonc/manifest.json
  ```
  *(Ví dụ: `http://192.168.88.37:7071/nguonc/manifest.json` - Cần nhấp chuột phải file `add_firewall_rule.bat` chọn **Run as administrator** để mở cổng 7071 trong Windows Firewall).*
* **Xem trên Stremio Web (`web.stremio.com`):**
  - Chạy file `run_online_tunnel.bat` (hoặc `npx localtunnel --port 7071`).
  - Mở link gốc `https://<subdomain>.loca.lt` trên trình duyệt ➔ Nhập IP xác nhận ➔ Bấm **Continue**.
  - Dán link manifest vào Stremio:
    ```text
    https://<subdomain>.loca.lt/nguonc/manifest.json
    ```

---

### 3. Các bước thêm Addon vào Stremio App

1. Mở ứng dụng **Stremio** trên Máy tính, Điện thoại hoặc Smart TV.
2. Vào mục **Addons** (Biểu tượng mảnh ghép) ➔ Chọn **Paste Addon URL**.
3. Dán đường dẫn Manifest URL ở trên vào và nhấn **Install**.
4. Chuyển sang mục **Discover (Khám phá)** ➔ Chọn **NguonC Phim (Cinema)** để trải nghiệm!

---

## 🛠️ Danh sách Endpoints API

| Endpoint | Mô tả |
| :--- | :--- |
| `GET /nguonc/manifest.json` | Cung cấp thông tin Manifest chuẩn Stremio Protocol |
| `GET /nguonc/catalog/{type}/{catalog_id}.json` | Lấy danh sách phim theo catalog (Phim Mới, Phim Lẻ, Phim Bộ, Thể Loại, Quốc Gia, Năm) |
| `GET /nguonc/catalog/{type}/{catalog_id}/search={keyword}.json` | Tìm kiếm phim theo từ khóa |
| `GET /nguonc/catalog/{type}/{catalog_id}/genre={filter}.json` | Lọc phim theo Thể loại, Quốc gia hoặc Năm |
| `GET /nguonc/meta/{type}/{id}.json` | Lấy chi tiết thông tin phim & danh sách tập |
| `GET /nguonc/stream/{type}/{id}.json` | Trích xuất link phát HLS (.m3u8) & Embed Player |
