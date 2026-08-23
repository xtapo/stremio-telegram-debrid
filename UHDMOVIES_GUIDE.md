# 💎 UHDMovies Cinema - Stremio Addon (4K UHD 2160p, 1080p HEVC, HDR DoVi)

Addon **UHDMovies** cho phép tìm kiếm và xem phim bom tấn Hollywood, Bollywood, Web Series chất lượng siêu cao **4K Ultra HD (2160p), 4K HDR, Dolby Vision, 1080p 10Bit HEVC, 60FPS**, hỗ trợ **Dual Audio (Hindi + English)** và phát trực tuyến tốc độ cao (Google Drive Direct CDN / Fast Stream) trên mọi thiết bị Stremio.

---

## ✨ Tính năng nổi bật của UHDMovies Addon

1. **Chất lượng Video Đỉnh cao (4K UHD, HDR, DoVi, 60FPS)**:
   - Kho phim 4K UHD 2160p (HDR10, Dolby Vision, SDR), 1080p 10Bit HEVC x265, 1080p 60FPS mượt mà và 720p HD.
   - Hỗ trợ đa âm thanh: Dual Audio (Hindi Org + English Org / Dolby Atmos / DDP 5.1) và phụ đề ESubs.

2. **Phát Trực Tiếp Tốc độ cao (Google Drive CDN / Fast Stream)**:
   - Tự động giải mã chuỗi liên kết (UnblockedGames ➔ DriveSeed ➔ Instant Download CDN).
   - Tích hợp 2 chế độ phát: **Direct Stream** (chuyển hướng 302 trực tiếp) và **Local Proxy Stream** hỗ trợ đầy đủ **HTTP Range 206 Partial Content** giúp tua / seek / scrub mượt mà trên Stremio (LibVLC / ExoPlayer).

3. **Hỗ trợ Mã IMDb (Cinemeta `tt...`) & Tìm kiếm Thông minh**:
   - Bạn có thể duyệt phim từ Catalogs phong phú của UHDMovies.
   - Khi bấm vào bất kỳ phim nào trong thư viện hoặc bảng xếp hạng mặc định của Stremio, addon sẽ tự động tìm kiếm trên UHDMovies và hiển thị nguồn stream tương ứng.

4. **Danh mục Khám phá (Discover) Đa dạng**:
   - **UHDMovies - Phim Mới Cập Nhật**: Cập nhật phim chiếu rạp và bom tấn mới nhất.
   - **UHDMovies - 4K HDR & Dolby Vision**: Kho phim 4K HDR sắc nét và sống động.
   - **UHDMovies - 2160p 4K HEVC**: Bản nén HEVC chuẩn 4K dung lượng tối ưu.
   - **UHDMovies - 1080p 10Bit HEVC**: Chuẩn màu 10-bit x265 chất lượng cao.
   - **UHDMovies - TV & Web Series**: Phim bộ dài tập nhiều mùa (Seasons) và tập (Episodes).
   - **Bộ lọc thể loại**: Phim Mới, 4K HDR, 2160p HEVC, 1080p 10Bit, Dual Audio, English Movies, IMAX, TV Series, Web Series, Collection...

5. **Tích hợp Tự động Dịch Phụ đề AI VietSub**:
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
  http://127.0.0.1:7860/uhdmovies/manifest.json
  ```
* **Xem từ thiết bị khác trong cùng mạng LAN / Wi-Fi (Smart TV, Android TV, Điện thoại):**
  ```text
  http://<IP_LAN_CUA_MAY_TINH>:7860/uhdmovies/manifest.json
  ```
  *(Ví dụ: `http://192.168.1.100:7860/uhdmovies/manifest.json`)*
* **Xem từ xa hoặc Stremio Web qua Tunnel (Cloudflare / Localtunnel / Render):**
  ```text
  https://<domain-cua-ban>/uhdmovies/manifest.json
  ```

---

### 3. Các bước thêm Addon vào Stremio App

1. Mở ứng dụng **Stremio** trên Máy tính, Điện thoại, Android TV hoặc Smart TV.
2. Vào mục **Addons** (biểu tượng mảnh ghép 🧩) ➔ Bấm **Community Addons** hoặc **Paste Addon URL**.
3. Dán đường dẫn Manifest URL ở trên vào và nhấn **Install**.
4. Chuyển sang mục **Discover (Khám phá)** ➔ Chọn nguồn **UHDMovies** để bắt đầu thưởng thức phim 4K UHD!

---

## ⚙️ Cấu hình Tùy chọn trong `.env`

| Biến Môi Trường | Mặc Định | Mô Tả |
| :--- | :--- | :--- |
| `ENABLE_SOURCE_UHDMOVIES` | `True` | Bật/tắt toàn bộ nguồn UHDMovies |
| `ENABLE_BOARD_UHDMOVIES` | `True` | Bật/tắt hiển thị danh mục UHDMovies trên Trang chủ (Board) của Stremio |
| `UHDMOVIES_BASE_URL` | `https://uhdmovies.autos` | Tên miền chính của trang UHDMovies |
