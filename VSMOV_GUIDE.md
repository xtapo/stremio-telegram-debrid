# 🎬 VSMov Cinema - Stremio Addon (HLS HD Trực Tiếp)

Hệ thống Addon VSMov cho phép tìm kiếm, xem phim lẻ, phim bộ Việt Nam chất lượng cao HD với đường truyền **HLS Trực Tiếp mượt mà 100% trên Trình phát mặc định của Stremio (LibVLC / ExoPlayer)**.

---

## ✨ Tính năng nổi bật của VSMov Addon

1. **Phát Trực Tiếp 100% trong Stremio**:
   - Sử dụng chuẩn HLS `.m3u8` trực tiếp.
   - Không bị vướng mã hóa Web Crypto.
   - Hoạt động mượt mà trên **Stremio Desktop (Windows/Mac), Android, iOS và Android TV**.

2. **Bộ lọc Khám Phá (Discover) Đầy Đủ**:
   - **Phim Mới Cập Nhật**: Cập nhật danh sách phim hot vừa phát hành liên tục.
   - **Phim Theo Thể Loại (20 thể loại)**: Hành Động, Tình Cảm, Hài, Kinh Dị, Hoạt Hình, Cổ Trang, Võ Thuật, Viễn Tưởng, Phiêu Lưu, Hình Sự, Tâm Lý, Học Đường, Bí Ẩn, Gia Đình, Thần Thoại, Chiến Tranh, Tài Liệu, Chính Kịch, Âm Nhạc, Phim 18+.
   - **Phim Theo Quốc Gia (14 quốc gia / khu vực)**: Trung Quốc, Hàn Quốc, Mỹ, Âu Mỹ, Nhật Bản, Thái Lan, Hồng Kông, Đài Loan, Việt Nam, Ấn Độ, Anh, Pháp, Đức, Nga.
   - **Danh mục Phim Bộ Chuyên Biệt**: Phim Trung Quốc, Phim Hàn Quốc, Phim Âu Mỹ.

3. **Danh sách Stream Đa dạng**:
   - **`▶ VSMov Proxy [Server]`**: Luồng Proxy tối ưu phát nội bộ trong Stremio.
   - **`⚡ VSMov Direct [Server]`**: Luồng HLS phát trực tiếp.
   - **`🌐 VSMov Web [Server]`**: Luồng dự phòng mở bằng trình duyệt web.

---

## 🚀 Hướng dẫn Khởi động & Cài đặt vào Stremio

### 1. Khởi động Máy chủ Addon

Trong cửa sổ Terminal (PowerShell), chạy lệnh khởi động máy chủ:

```powershell
python nguonc_router.py
```
*(Server chạy trên cổng `7071` tích hợp cả VSMov Addon lẫn NguonC Addon)*

---

### 2. Đường dẫn Cài đặt Manifest URL (Stremio)

Tùy vào thiết bị và môi trường của bạn:

* **Xem trên cùng máy tính (Stremio Desktop App):**
  ```text
  http://127.0.0.1:7071/vsmov/manifest.json
  ```
* **Xem từ thiết bị khác trong cùng mạng Wi-Fi/LAN (Điện thoại, Smart TV, Android TV, iPad...):**
  ```text
  http://<IP_LAN_CUA_MAY_TINH>:7071/vsmov/manifest.json
  ```
  *(Ví dụ: `http://192.168.88.37:7071/vsmov/manifest.json` - Cần nhấp chuột phải file `add_firewall_rule.bat` chọn **Run as administrator** để mở cổng 7071 trong Windows Firewall).*
* **Xem trên Stremio Web (`web.stremio.com`):**
  - Chạy file `run_online_tunnel.bat` (hoặc `npx localtunnel --port 7071`).
  - Mở link gốc `https://<subdomain>.loca.lt` trên trình duyệt ➔ Nhập IP xác nhận ➔ Bấm **Continue**.
  - Dán link manifest vào Stremio:
    ```text
    https://<subdomain>.loca.lt/vsmov/manifest.json
    ```

---

### 3. Các bước thêm Addon vào Stremio App

1. Mở ứng dụng **Stremio** trên Máy tính, Điện thoại hoặc Smart TV.
2. Vào mục **Addons** (Biểu tượng mảnh ghép) ➔ Chọn **Paste Addon URL**.
3. Dán đường dẫn Manifest URL ở trên vào và nhấn **Install**.
4. Chuyển sang mục **Discover (Khám phá)** ➔ Chọn **VSMov - Phim Miễn Phí** để trải nghiệm!

---

## 🐧 Hướng dẫn Chạy Ngầm 24/7 trên Linux / VPS (PM2 & Cloudflare)

Nếu triển khai máy chủ Addon trên hệ điều hành Linux (Ubuntu, Debian, CentOS...) hoặc VPS:

### 1. Cài đặt môi trường (Python 3, Node.js & PM2)

```bash
sudo apt update && sudo apt install python3 python3-pip nodejs npm -y
sudo npm install -g pm2
```

### 2. Cài đặt Cloudflare Tunnel (`cloudflared`)

```bash
# Dành cho VPS Intel / AMD (amd64 / x86_64):
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && dpkg -i cloudflared.deb

# Dành cho VPS ARM (Oracle Cloud ARM...):
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb && dpkg -i cloudflared.deb
```

### 3. Khởi chạy ngầm 24/7 bằng PM2

```bash
# 1. Khởi chạy Server Python Addon
pm2 start nguonc_router.py --name "cinema-addon" --interpreter python3

# 2. Khởi chạy Cloudflare Tunnel (Tạo đường dẫn HTTPS)
pm2 start cloudflared --name "cloudflare-tunnel" -- tunnel --url http://localhost:7071

# 3. Xem log để lấy địa chỉ HTTPS (trycloudflare.com)
pm2 logs cloudflare-tunnel

# 4. Lưu lại cấu hình để tự khởi động cùng Linux/VPS khi reboot
pm2 save && pm2 startup
```

---

## 🛠️ Danh sách Endpoints API

| Endpoint | Mô tả |
| :--- | :--- |
| `GET /vsmov/manifest.json` | Cung cấp thông tin Manifest chuẩn Stremio Protocol |
| `GET /vsmov/catalog/{type}/{id}.json` | Lấy danh sách phim theo catalog (Phim Mới, Thể Loại, Quốc Gia, Trung Quốc, Hàn Quốc, Âu Mỹ) |
| `GET /vsmov/catalog/{type}/{id}/search={keyword}.json` | Tìm kiếm phim theo từ khóa |
| `GET /vsmov/catalog/{type}/{id}/genre={filter}.json` | Lọc phim theo Thể loại hoặc Quốc gia |
| `GET /vsmov/meta/{type}/{id}.json` | Lấy chi tiết thông tin phim & danh sách tập |
| `GET /vsmov/stream/{type}/{id}.json` | Trích xuất link phát HLS (.m3u8) & Embed Player |
| `GET /vsmov/stream_proxy` | Proxy mã hóa luồng HLS cho trình phát Stremio |
