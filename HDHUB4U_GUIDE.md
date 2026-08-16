# ⚡ HDHub4u Cinema - Stremio Addon (4K UHD & Dual Audio)

Addon **HDHub4u** cho phép tìm kiếm và xem phim bom tấn Hollywood, Bollywood, Netflix, Disney+, Amazon Prime chất lượng cao **4K UHD (2160p), 1080p FHD, 720p HD**, hỗ trợ **Dual Audio (Hindi + English / Original)** và phát trực tuyến tốc độ cao (Cloudflare R2 10Gbps, Pixel CDN) trên mọi thiết bị Stremio.

---

## ✨ Tính năng nổi bật của HDHub4u Addon

1. **Kho phim 4K UHD, 1080p, 720p & Dual Audio**:
   - Kho phim 4K UHD 2160p (HDR / DV / SDR), 1080p HEVC x265, 720p và 480p phong phú.
   - Hỗ trợ đa âm thanh: Dual Audio (Hindi Org + English Org) và phụ đề ESub.

2. **Phát Trực Tiếp Tốc độ cao 10Gbps (Cloudflare R2)**:
   - Sử dụng máy chủ phân phối Cloudflare R2 direct stream / Pixel CDN.
   - Tích hợp 2 chế độ phát: **Direct Stream** (chuyển hướng 302 siêu nhanh) và **Local Proxy Stream** hỗ trợ đầy đủ **HTTP Range 206 Partial Content** giúp tua / seek / scrub mượt mà trên Stremio (LibVLC / ExoPlayer).

3. **Hỗ trợ Mã IMDb (Cinemeta `tt...`) & Tìm kiếm Thông minh**:
   - Bạn có thể duyệt phim từ Catalogs của HDHub4u.
   - Hoặc khi bạn bấm vào bất kỳ phim nào trong thư viện / bảng xếp hạng mặc định của Stremio, addon sẽ tự động tìm kiếm trên HDHub4u và hiển thị nguồn stream tốc độ cao.

4. **Hệ thống Dynamic Mirror & Auto Host Discovery**:
   - Tự động truy vấn và phân giải tên miền hoạt động mới nhất của HDHub4u qua API trung gian (`h4.suncdn.org`, `points.topapii.com`, `ml.theapii.org`, `dns.pingora.fyi`), không lo trang web đổi tên miền hay bị chặn.

5. **Danh mục Khám phá (Discover) Đa dạng**:
   - **HDHub4u - Phim Mới Cập Nhật**: Cập nhật phim chiếu rạp và web series hot nhất.
   - **HDHub4u - Hollywood Movies**: Kho phim bom tấn Hollywood Âu Mỹ.
   - **HDHub4u - Bollywood Movies**: Phim điện ảnh Ấn Độ đặc sắc.
   - **HDHub4u - Phim Bộ (Web Series)**: Hỗ trợ các bộ phim dài tập nhiều mùa (Seasons) và tập (Episodes).
   - **Bộ lọc 20 thể loại**: Action, Adventure, Animation, Comedy, Crime, Drama, Fantasy, Horror, Romance, Sci-Fi, Thriller, 300MB, 18+, v.v.

---

## 🚀 Hướng dẫn Cài đặt vào Stremio

### 1. Khởi động Máy chủ Addon

Bạn có thể chạy riêng HDHub4u router hoặc chạy server chính `addon.py`:

```powershell
# Chạy server chính tích hợp toàn bộ addon (Telegram, Debrid, MoviesDrive, HDHub4u, NguonC, VSMov, TopXX):
python addon.py

# Hoặc chạy độc lập riêng HDHub4u router:
python hdhub4u_router.py
```

---

### 2. Đường dẫn Manifest URL (Stremio)

Tùy vào cổng chạy và môi trường mạng của bạn:

* **Chạy cùng server chính `addon.py` (Cổng `7860` hoặc cổng bạn cấu hình):**
  ```text
  http://127.0.0.1:7860/hdhub4u/manifest.json
  ```
* **Chạy độc lập `hdhub4u_router.py` (Cổng `7005`):**
  ```text
  http://127.0.0.1:7005/hdhub4u/manifest.json
  ```
* **Xem từ thiết bị khác trong cùng mạng LAN / Wi-Fi (Smart TV, Android TV, Điện thoại):**
  ```text
  http://<IP_LAN_CUA_MAY_TINH>:7860/hdhub4u/manifest.json
  ```
  *(Ví dụ: `http://192.168.1.100:7860/hdhub4u/manifest.json`)*
* **Xem từ xa hoặc Stremio Web qua Tunnel (Cloudflare / Localtunnel / Ngrok):**
  ```text
  https://<domain-cua-ban>/hdhub4u/manifest.json
  ```

---

### 3. Các bước thêm Addon vào Stremio App

1. Mở ứng dụng **Stremio** trên Máy tính, Điện thoại, Android TV hoặc Smart TV.
2. Vào mục **Addons** (biểu tượng mảnh ghép 🧩) ➔ Chọn **Community Addons** hoặc bấm **Paste Addon URL**.
3. Dán đường dẫn Manifest URL ở trên vào và nhấn **Install**.
4. Chuyển sang mục **Discover (Khám phá)** ➔ Chọn nguồn **HDHub4u** để bắt đầu thưởng thức phim 4K!
