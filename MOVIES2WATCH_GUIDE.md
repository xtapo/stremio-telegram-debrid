# 🎬 Hướng Dẫn Tích Hợp Nguồn Movies2Watch (movies2watch.vc)

Nguồn phim & series truyền hình quốc tế **Movies2Watch** (`https://movies2watch.vc/`) đã được tích hợp sẵn vào hệ sinh thái Stremio Addon với khả năng duyệt phim lẻ, phim bộ, lọc thể loại, quốc gia, tìm kiếm và phát đa máy chủ tốc độ cao (UpCloud, Vidmoly, Videasy, Vidsrc, Vidfast).

---

## 🌟 Tính Năng Nổi Bật

- **Kho Phim Đa Dạng**: Phim lẻ chiếu rạp mới nhất (Movies), TV Series nhiều mùa/tập, bảng xếp hạng phim thịnh hành (Trending / Home).
- **Bộ Lọc Toàn Diện**: Lọc nhanh theo 28+ thể loại (Action, Adventure, Animation, Comedy, Crime, Sci-Fi, Horror...) và 30+ quốc gia (Mỹ, Anh, Pháp, Hàn Quốc, Nhật Bản, Tây Ban Nha...).
- **Hỗ Trợ Mùa & Tập (Seasons & Episodes)**: Tự động trích xuất thông tin mùa và từng tập phim với tiêu đề đầy đủ.
- **Đa Máy Chủ Phát (Multi-Server)**:
  - **UpCloud** / **Vidmoly** / **Videasy** / **Vidsrc** / **Vidfast**.
  - Tự động trích xuất mã IMDb / TMDB để kích hoạt luồng phát HLS Full HD / 4K tốc độ cao kèm phụ đề đa ngôn ngữ.
- **Tương Thích Mọi Thiết Bị**: Phát mượt mà trên Stremio Desktop, Android TV, Google TV, Web Player, iOS, FireStick.

---

## 🚀 Đường Dẫn Cài Đặt Stremio Addon

Sau khi khởi động server, bạn có thể thêm trực tiếp manifest sau vào Stremio:

```text
http://127.0.0.1:7860/movies2watch/manifest.json
```

Hoặc qua mạng LAN / Domain công khai:
```text
http://<LAN_IP>:7860/movies2watch/manifest.json
https://<YOUR_DOMAIN>/movies2watch/manifest.json
```

---

## ⚙️ Cấu Hình Môi Trường (`.env`)

Bạn có thể tùy chỉnh nguồn Movies2Watch trong file `.env`:

```ini
# Bật/Tắt nguồn Movies2Watch (Mặc định: True)
ENABLE_SOURCE_MOVIES2WATCH=True

# Bật/Tắt hiển thị danh mục Movies2Watch trên Trang chủ (Board) của Stremio (Mặc định: True)
ENABLE_BOARD_MOVIES2WATCH=True

# Tên miền chính Movies2Watch (Mặc định: https://movies2watch.vc)
MOVIES2WATCH_BASE_URL=https://movies2watch.vc
```

---

## 📡 Các Điểm Cuối API (Routes)

| Route | Phương Thức | Chức Năng |
|---|---|---|
| `/movies2watch/manifest.json` | `GET` | Cung cấp manifest Stremio cho nguồn Movies2Watch |
| `/movies2watch/catalog/{type}/{id}.json` | `GET` | Danh mục phim lẻ, TV shows, tìm kiếm & bộ lọc |
| `/movies2watch/meta/{type}/{id}.json` | `GET` | Chi tiết phim, hình ảnh, poster, danh sách tập/mùa |
| `/movies2watch/stream/{type}/{id}.json` | `GET` | Trích xuất các luồng phát video đa máy chủ |
| `/movies2watch/stream_proxy` | `GET` | Proxy phát luồng HLS / Range Requests chống chặn |
