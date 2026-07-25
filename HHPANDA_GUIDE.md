# 🐼 HHPanda - Hoạt Hình 3D Trung Quốc 4K Addon (Stremio)

Addon **HHPanda** cho phép tìm kiếm và xem hàng ngàn bộ phim **Hoạt Hình 3D Trung Quốc (HH3D) VietSub chất lượng 4K / Full HD** sắc nét không quảng cáo trên trình phát Stremio.

---

## ✨ Tính năng nổi bật

1. **Chuyên biệt Hoạt Hình 3D Trung Quốc**:
   - Cập nhật liên tục các bộ phim HH3D cực hot: *Tiên Nghịch, Đấu Phá Thương Khung, Thế Giới Hoàn Mỹ, Phàm Nhân Tu Tiên, Già Thiên, Mục Thần Ký, Thôn Phệ Tinh Không...*
   - Chất lượng siêu nét 4K / 1080P với VietSub chuẩn.

2. **Bộ lọc Khám Phá (Discover)**:
   - **Mới Cập Nhật**: Phim mới vừa ra tập mới nhất.
   - **Phim Theo Thể Loại**: Tu Tiên, Kiếm Hiệp, Cổ Trang, Huyền Huyễn, Khoa Huyễn, Kỳ Ảo, Huyền Nghi, Cạnh Kỹ, Dã Sử, Đô Thị, Đồng Nhân.
   - **Phim Hoàn Thành**: Các bộ phim đã chiếu trọn bộ.
   - **Top Xem Nhiều**: Các phim được yêu thích nhất.

3. **Luồng phát mượt mà trên Stremio**:
   - `▶ HHPanda 1080P (Proxy Embed)`: Tối ưu xem trực tiếp trong Stremio app.
   - `🌐 HHPanda Web Stream`: Mở luồng phát trực tiếp qua trình duyệt web.

---

## 🚀 Hướng dẫn Khởi động & Cài đặt vào Stremio

### 1. Khởi động Máy chủ Addon

Trong terminal (PowerShell), khởi động máy chủ Addon:

```powershell
python nguonc_router.py
```
*(Máy chủ chạy cổng `7071` phục vụ đồng thời các Addon: NguonC, VSMov, TopXX và HHPanda)*

---

### 2. Đường dẫn Manifest URL (Stremio)

- **Xem trên cùng máy tính (Stremio Desktop App):**
  ```text
  http://127.0.0.1:7071/hhpanda/manifest.json
  ```
- **Xem từ thiết bị khác trong cùng mạng Wi-Fi/LAN (Điện thoại, Smart TV, Android TV, iPad...):**
  ```text
  http://<IP_LAN_CUA_MAY_TINH>:7071/hhpanda/manifest.json
  ```
  *(Ví dụ: `http://192.168.1.15:7071/hhpanda/manifest.json`)*

- **Xem trên Stremio Web (`web.stremio.com`):**
  - Khởi chạy Cloudflare Tunnel hoặc Localtunnel:
    ```text
    https://<your-subdomain>.loca.lt/hhpanda/manifest.json
    ```

---

### 3. Các bước thêm vào Stremio App

1. Mở ứng dụng **Stremio**.
2. Chọn biểu tượng **Addons** (Mảnh ghép) ➔ Bấm **Paste Addon URL**.
3. Dán link Manifest ở trên vào và bấm **Install**.
4. Vào mục **Discover (Khám phá)** ➔ Chọn **HHPanda - Hoạt Hình 3D 4K** để thưởng thức!
