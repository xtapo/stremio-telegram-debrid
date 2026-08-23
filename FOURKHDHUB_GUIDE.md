# 🎬 4KHDHub Cinema - Stremio Addon (4K Ultra HD, Dolby Vision, HDR10+, 1080p HEVC)

Addon **4KHDHub** cho phép tìm kiếm và xem phim bom tấn Hollywood, Bollywood, Netflix, Amazon Prime Video, Disney+, Apple TV+, HBO Max, Anime và Web Series chất lượng siêu cao **4K Ultra HD (2160p), Dolby Vision (DV), HDR10+, 1080p HEVC REMUX**, hỗ trợ **Dual Audio (Hindi + English / Dolby Atmos / DDP 5.1)** và phát trực tuyến tốc độ cao (**Cloudflare R2 10Gbps / HubCloud 10Gbps CDN / PixelDrain**) trên mọi thiết bị Stremio.

---

## ✨ Tính năng nổi bật của 4KHDHub Addon

1. **Chất lượng Video Đỉnh cao (4K UHD 2160p, Dolby Vision, HDR10+, REMUX)**:
   - Kho phim 4K UHD 2160p (Dolby Vision, HDR10+, SDR), 1080p HEVC x265, 1080p REMUX chất lượng gốc và 720p HD.
   - Hỗ trợ đa âm thanh: Dual Audio (Hindi + English / Dolby Atmos / DDP 5.1 / DTS-HD) và phụ đề đa ngôn ngữ.

2. **Phát Trực Tiếp Tốc độ cao (Cloudflare R2 10Gbps / HubCloud GPDL CDN)**:
   - Tự động giải mã chuỗi liên kết (HubCloud / HubDrive ➔ GamerXYT ➔ Instant Download CDN / Cloudflare R2).
   - Tích hợp 2 chế độ phát: **Direct Stream** (chuyển hướng 302 trực tiếp đến CDN) và **Local Proxy Stream** hỗ trợ đầy đủ **HTTP Range 206 Partial Content** giúp tua / seek / scrub mượt mà trên Stremio (LibVLC / ExoPlayer).

3. **Hỗ trợ Mã IMDb (Cinemeta `tt...`) & Tìm kiếm Thông minh**:
   - Bạn có thể duyệt phim từ Catalogs phong phú của 4KHDHub.
   - Khi bấm vào bất kỳ phim nào trong thư viện hoặc bảng xếp hạng mặc định của Stremio, addon sẽ tự động tìm kiếm trên 4KHDHub và hiển thị nguồn stream tương ứng.

4. **Danh mục Khám phá (Discover) Đa dạng**:
   - **4KHDHub - Phim Mới Cập Nhật**: Cập nhật phim chiếu rạp và bom tấn mới nhất.
   - **4KHDHub - 4K HDR & Dolby Vision**: Kho phim 4K HDR & Dolby Vision sắc nét sống động.
   - **4KHDHub - English Movies 4K**: Phim lẻ tiếng Anh chất lượng cao 4K / 1080p.
   - **4KHDHub - Web Series & TV Shows 4K**: Phim bộ dài tập nhiều mùa (Seasons) và tập (Episodes).
   - **Bộ lọc thể loại**: Phim Mới, 4K HDR, English Movies, Hindi Movies, Web Series, English Series, Hindi Series, Korean Series, Drama Series, Netflix, Amazon Prime Video, Disney+, HBO Max, Anime, Top IMDb...

5. **Tích hợp Tự động Dịch Phụ đề AI VietSub & Thuyết minh**:
   - Tự động tạo 2 luồng phụ đề tiếng Việt (Nhanh và AI chất lượng cao) đồng bộ thời gian chuẩn xác.

---

## 🚀 Hướng dẫn Cài đặt vào Stremio

### 1. Khởi động Máy chủ Addon

Chạy server chính tích hợp toàn bộ addon:

```powershell
python addon.py
```

---

### 2. Đường dẫn Manifest URL (Stremio)

Tùy vào cổng chạy và môi trường mạng của bạn:

* **Chạy cục bộ trên máy tính (Cổng `7860`):**
  ```text
  http://127.0.0.1:7860/4khdhub/manifest.json
  ```
* **Xem từ thiết bị khác trong cùng mạng LAN / Wi-Fi (Smart TV, Android TV, Điện thoại):**
  ```text
  http://<IP_LAN_CUA_MAY_TINH>:7860/4khdhub/manifest.json
  ```
  *(Ví dụ: `http://192.168.1.100:7860/4khdhub/manifest.json`)*
* **Xem từ xa hoặc Stremio Web qua Tunnel (Cloudflare / Localtunnel / Render):**
  ```text
  https://<domain-cua-ban>/4khdhub/manifest.json
  ```

---

### 3. Các bước thêm Addon vào Stremio App

1. Mở ứng dụng **Stremio** trên Máy tính, Điện thoại, Android TV hoặc Smart TV.
2. Vào mục **Addons** (biểu tượng mảnh ghép 🧩) ➔ Bấm **Community Addons** hoặc **Paste Addon URL**.
3. Dán đường dẫn Manifest URL ở trên vào và nhấn **Install**.
4. Chuyển sang mục **Discover (Khám phá)** ➔ Chọn nguồn **4KHDHub** để bắt đầu thưởng thức phim 4K UHD!

---

## ⚙️ Cấu hình Tùy chọn trong `.env`

| Biến Môi Trường | Mặc Định | Mô Tả |
| :--- | :--- | :--- |
| `ENABLE_SOURCE_4KHDHUB` | `True` | Bật/tắt toàn bộ nguồn 4KHDHub |
| `ENABLE_BOARD_4KHDHUB` | `True` | Bật/tắt hiển thị danh mục 4KHDHub trên Trang chủ (Board) của Stremio |
| `FOURKHDHUB_BASE_URL` | `https://4khdhub.one` | Tên miền chính của trang 4KHDHub |
