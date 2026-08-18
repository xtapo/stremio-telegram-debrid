# 🌐 HDToday Cinema - Stremio Addon (Phim & Series Quốc Tế Full HD)

Hệ thống Addon **HDToday** tích hợp kho phim và series truyền hình quốc tế đồ sộ từ [HDToday (hdtoday.sc)](https://hdtoday.sc/), hỗ trợ xem phim lẻ (Movies) và phim bộ (TV Series) chất lượng cao Full HD / 4K kèm chuẩn **HLS Streaming Proxy phát trực tiếp 100% trên Trình phát mặc định của Stremio (LibVLC / ExoPlayer)** cùng hệ thống đa âm thanh và phụ đề đa ngôn ngữ.

---

## ✨ Tính năng nổi bật của HDToday Addon

1. **Kho nội dung Quốc tế Đồ sộ**:
   - Kho phim bom tấn Hollywood, Âu Mỹ, Châu Á, Anime và các Series truyền hình ăn khách nhất thế giới.
   - Cập nhật liên tục các tập phim mới nhất mỗi ngày.

2. **Phát Trực Tiếp 100% trong Stremio (HLS Proxy)**:
   - Tự động trích xuất và giải mã Master HLS Playlist `.m3u8` từ các cụm server cao cấp (VixCloud / VixSrc / UpCloud...).
   - **Tích hợp HLS Stream Proxy**: Tự động xử lý Referer, Origin và CORS Headers giúp Stremio Desktop, Android, iOS, Android TV và Web Player phát mượt mà không bao giờ bị chặn.

3. **Hỗ trợ Đa Âm Thanh & Đa Phụ Đề (Multi-Audio & Multi-Subtitles)**:
   - Các bản phim/series đi kèm nhiều track âm thanh (English, Italian, Spanish, French, German, ...) và phụ đề đa ngôn ngữ.

4. **Bộ lọc Khám Phá (Discover) Chuẩn Stremio**:
   - **HDToday - Latest Movies**: Danh sách phim lẻ mới cập nhật.
   - **HDToday - Latest TV Shows**: Danh sách phim bộ / truyền hình mới cập nhật.
   - **HDToday - Top IMDb**: Danh sách các tác phẩm có điểm đánh giá IMDb cao nhất.
   - **HDToday - Movies & Series by Genre (26 thể loại)**: Action, Adventure, Animation, Comedy, Crime, Documentary, Drama, Family, Fantasy, History, Horror, Kids, Music, Mystery, News, Reality, Romance, Sci-Fi, Thriller, War, Western...
   - **HDToday - Movies & Series by Country (35+ quốc gia)**: Mỹ, Anh, Nhật Bản, Hàn Quốc, Pháp, Đức, Canada, Úc, Trung Quốc, Thái Lan, Tây Ban Nha, Ý, Brazil...
   - **Tìm kiếm thông minh (Search)**: Tìm kiếm phim lẻ và phim bộ theo tên tức thì.

---

## 🚀 Hướng dẫn Khởi động & Cài đặt vào Stremio

### 1. Cấu hình Biến Môi Trường (`.env`)

```ini
# Bật/Tắt nguồn HDToday
ENABLE_SOURCE_HDTODAY=True

# Bật/Tắt hiển thị danh mục HDToday trên Trang chủ (Board) của Stremio
ENABLE_BOARD_HDTODAY=True

# Tùy chọn thay đổi domain HDToday nếu cần
HDTODAY_BASE_URL=https://hdtoday.sc
```

---

### 2. Khởi động Máy chủ Addon

Trong cửa sổ Terminal (PowerShell):

```powershell
python addon.py
```

---

### 3. Đường dẫn Cài đặt Manifest URL (Stremio)

Tùy vào thiết bị và môi trường:

* **Xem trên cùng máy tính (Stremio Desktop App):**
  ```text
  http://127.0.0.1:7860/hdtoday/manifest.json
  ```
* **Xem từ thiết bị khác trong cùng mạng Wi-Fi/LAN (Điện thoại, Smart TV, Android TV, iPad...):**
  ```text
  http://<IP_LAN_CUA_MAY_TINH>:7860/hdtoday/manifest.json
  ```
  *(Ví dụ: `http://192.168.1.100:7860/hdtoday/manifest.json`)*
* **Xem qua Public Domain / VPS / Cloudflare Tunnel:**
  ```text
  https://your-domain.com/hdtoday/manifest.json
  ```

---

### 4. Các bước thêm Addon vào Stremio App

1. Mở ứng dụng **Stremio** trên Máy tính, Điện thoại hoặc Smart TV.
2. Vào mục **Addons** (Biểu tượng mảnh ghép) ➔ Chọn **Paste Addon URL**.
3. Dán đường dẫn Manifest URL ở trên vào và nhấn **Install**.
4. Chuyển sang mục **Discover (Khám phá)** ➔ Chọn **HDToday - Movies & TV Series HD** để thưởng thức!
