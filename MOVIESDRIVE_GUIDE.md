# 🎬 MoviesDrive Cinema - Stremio Addon (4K UHD & Dual Audio)

Addon **MoviesDrive** cho phép tìm kiếm và xem phim bom tấn Hollywood, Bollywood, Netflix, Disney+, Amazon Prime chất lượng cao **4K UHD (2160p), 1080p FHD, 720p HD**, hỗ trợ **Dual Audio (Hindi + English / Original)** và phát trực tuyến tốc độ cao 10Gbps (Cloudflare Workers / Google CDN) trên mọi thiết bị Stremio.

---

## ✨ Tính năng nổi bật của MoviesDrive Addon

1. **Chất lượng Video Đỉnh cao (4K UHD, 1080p, 720p)**:
   - Kho phim 4K UHD 2160p (HDR / DV / SDR) phong phú.
   - Hỗ trợ đa âm thanh: Dual Audio (Hindi Org + English Org) và phụ đề ESub.

2. **Phát Trực Tiếp Tốc độ cao 10Gbps**:
   - Sử dụng máy chủ phân phối Cloudflare Workers / Pixel / Google CDN.
   - Tích hợp Proxy stream hỗ trợ đầy đủ **HTTP Range 206 Partial Content** giúp tua / seek / scrub nhanh không bị giật lag trên Stremio (LibVLC / ExoPlayer).

3. **Hỗ trợ Mã IMDb (Cinemeta `tt...`) & Tìm kiếm Thông minh**:
   - Bạn có thể duyệt phim từ Catalogs của MoviesDrive.
   - Hoặc khi bạn bấm vào bất kỳ phim nào trong thư viện / bảng xếp hạng mặc định của Stremio, addon sẽ tự động tìm kiếm và hiển thị nguồn stream từ MoviesDrive.

4. **Danh mục Khám phá (Discover) Đa dạng**:
   - **MoviesDrive - Phim Mới**: Cập nhật phim chiếu rạp và web series hot nhất.
   - **MoviesDrive - Phim 4K UHD**: Danh mục dành riêng cho các tín đồ xem phim màn hình lớn 4K.
   - **MoviesDrive - Phim Bộ (Series)**: Hỗ trợ phim bộ nhiều mùa (Seasons) và tập (Episodes).
   - **26 Thể loại chọn lọc**: Action, Adventure, Animation, Anime, Bollywood, Comedy, Crime, Documentary, Drama, Dual Audio, DV HDR, Family, Fantasy, Hindi Dubbed, Hollywood, Horror, IMAX, K-Drama, Mystery, Netflix, Romance, Sci-Fi, South, Thriller, War, 2160p 4K.

---

## 🚀 Hướng dẫn Cài đặt vào Stremio

### 1. Khởi động Máy chủ Addon

Bạn có thể chạy riêng MoviesDrive router hoặc chạy server chính `addon.py`:

```powershell
# Chạy server chính tích hợp toàn bộ addon (Telegram, Debrid, NguonC, VSMov, TopXX, MoviesDrive):
python addon.py

# Hoặc chạy độc lập riêng MoviesDrive router:
python moviesdrive_router.py
```

---

### 2. Đường dẫn Manifest URL (Stremio)

Tùy vào cổng chạy và môi trường mạng của bạn:

* **Chạy cùng server chính `addon.py` (Cổng `7000` hoặc cổng bạn cấu hình):**
  ```text
  http://127.0.0.1:7000/moviesdrive/manifest.json
  ```
* **Chạy độc lập `moviesdrive_router.py` (Cổng `7004`):**
  ```text
  http://127.0.0.1:7004/moviesdrive/manifest.json
  ```
* **Xem từ thiết bị khác trong cùng mạng LAN / Wi-Fi (Smart TV, Android TV, Điện thoại):**
  ```text
  http://<IP_LAN_CUA_MAY_TINH>:7000/moviesdrive/manifest.json
  ```
  *(Ví dụ: `http://192.168.1.100:7000/moviesdrive/manifest.json`)*
* **Xem từ xa hoặc Stremio Web qua Tunnel (Cloudflare / Localtunnel / Ngrok):**
  ```text
  https://<domain-cua-ban>/moviesdrive/manifest.json
  ```

---

### 3. Các bước thêm Addon vào Stremio App

1. Mở ứng dụng **Stremio** trên Máy tính, Điện thoại, Android TV hoặc Smart TV.
2. Vào mục **Addons** (biểu tượng mảnh ghép 🧩) ➔ Chọn **Community Addons** hoặc bấm **Paste Addon URL**.
3. Dán đường dẫn Manifest URL ở trên vào và nhấn **Install**.
4. Chuyển sang mục **Discover (Khám phá)** ➔ Chọn nguồn **MoviesDrive** để bắt đầu thưởng thức phim 4K!
