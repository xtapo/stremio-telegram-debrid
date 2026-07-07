# Hướng Dẫn Tích Hợp qBittorrent (Miễn Phí & Tự Lưu Trữ)

Tài liệu này hướng dẫn chi tiết cách thiết lập giao diện Web UI của qBittorrent, cấu hình file `.env` của addon và cách hoạt động của cơ chế phát trực tiếp (on-the-fly streaming) kèm tự động lưu trữ lên kênh Telegram.

---

## 1. Cấu hình Web UI trên qBittorrent

Để addon có thể thêm magnet link và kiểm soát tiến trình tải, bạn phải bật giao diện điều khiển qua Web (Web UI) của qBittorrent:

1. Mở phần mềm **qBittorrent** trên máy tính hoặc máy chủ của bạn.
2. Trên thanh menu, chọn **Tools** (Công cụ) > **Options** (Tùy chọn) (hoặc phím tắt `Alt + O`).
3. Chọn tab **Web UI** trong danh sách bên trái.
4. Tích chọn ô **Web User Interface (Remote control)** ở trên cùng.
5. Cấu hình các thông số kết nối:
   * **IP Address (Địa chỉ IP):** Mặc định để trống hoặc `*` (để lắng nghe trên mọi địa chỉ).
   * **Port (Cổng):** Mặc định là `8080` (bạn có thể đổi thành cổng khác nếu bị trùng).
   * **Authentication (Xác thực):** Điền **Username** (Tài khoản) và **Password** (Mật khẩu) bạn muốn dùng để đăng nhập.
6. Cuộn xuống dưới cùng và nhấn **Apply** > **OK** để áp dụng thay đổi.

---

## 2. Cấu hình file `.env` của Addon

Mở file `.env` trong thư mục gốc của addon và điền các tham số sau:

```env
# URL kết nối tới Web UI của qBittorrent (Đảm bảo đúng Port ở Bước 1)
QBITTORRENT_URL=http://localhost:8080

# Tài khoản và mật khẩu Web UI đã thiết lập ở Bước 1
QBITTORRENT_USER=admin
QBITTORRENT_PASS=mat_khau_cua_ban

# Thư mục chứa phim tải về (Đọc kỹ phần cấu hình Docker ở dưới nếu bạn chạy Docker)
QBITTORRENT_PLAY_DIR=

# Tự động tải từ qBittorrent xong sẽ upload lưu trữ lên Telegram (Khuyên dùng: True)
AUTO_UPLOAD_TO_TELEGRAM=True
```

---

## 3. Cách hoạt động của luồng Phát & Caching

Khi bạn tìm kiếm một bộ phim trên Stremio và chọn nguồn có nhãn **`[TG Local qBit]`**:

1. **Thêm và Tải tuần tự:** Addon sẽ tự động kết nối qua API gửi magnet link tới qBittorrent. Addon tự động thiết lập:
   * **Sequential Download (Tải tuần tự):** Tải các mảnh (pieces) file từ đầu đến cuối một cách tuần tự (giống như xem video YouTube), thay vì tải ngẫu nhiên như torrent thông thường.
   * **First/Last Piece Priority (Ưu tiên mảnh đầu/cuối):** Giúp tải nhanh phần header của file video giúp trình phát (Stremio) đọc được siêu dữ liệu (metadata) của phim nhanh nhất và khởi chạy trình phát ngay lập tức.
2. **Stream trực tiếp từ đĩa:** Trình phát Stremio sẽ gửi các Range Request (yêu cầu phân đoạn bytes). Addon sẽ đọc trực tiếp từ file đang tải trên đĩa cứng local để truyền lên Stremio.
   * **Cơ chế Chống Đơ (Anti-Stall):** Nếu người dùng tua hoặc xem nhanh hơn tốc độ tải của qBittorrent, trình phát của addon sẽ tự động ngưng đọc và chờ (sleep) cho đến khi qBittorrent tải thêm dữ liệu về đĩa rồi mới tiếp tục stream, ngăn ngừa lỗi đứng hình trên Stremio.
3. **Đẩy lên Telegram & Dọn dẹp ổ cứng:** Sau khi xem xong, qBittorrent vẫn tiếp tục tải ngầm cho đến khi đạt **100%**. Ngay khi tải xong, một tác vụ chạy nền của addon sẽ:
   * Tự động upload file đó lên kênh Telegram riêng tư của bạn.
   * Khi upload thành công, addon tự động gọi lệnh xóa torrent và tệp tin đã tải trong qBittorrent để giải phóng hoàn toàn dung lượng đĩa cứng local của bạn.

---

## 4. Cấu hình Docker Path Mapping (Ánh xạ đường dẫn)

Nếu bạn chạy Addon trong một Container Docker riêng và qBittorrent trong một Container/máy chủ khác, đường dẫn thư mục tải xuống (Save Path) sẽ khác nhau giữa hai bên.

* **Ví dụ:**
  * qBittorrent tải file và lưu vào thư mục bên trong container của nó là: `/downloads`.
  * Bạn mount thư mục download đó vào container của Addon tại đường dẫn: `/downloads_addon`.

Trong trường hợp này, bạn phải cấu hình biến:
```env
QBITTORRENT_PLAY_DIR=/downloads_addon
```
Addon sẽ tự động bỏ qua thư mục lưu gốc của qBittorrent và map tệp tin trực tiếp vào `/downloads_addon` để đọc file và stream.
