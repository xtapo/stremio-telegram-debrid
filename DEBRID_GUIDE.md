# Hướng Dẫn Tích Hợp Các Dịch Vụ Debrid (Real-Debrid & TorBox)

Dự án Stremio Telegram Addon hỗ trợ tích hợp các nhà cung cấp Debrid đám mây chuyên nghiệp để giải mã link torrent tức thì, phát trực tuyến không giật lag qua CDN tốc độ cao và tự động tải lưu trữ về kênh Telegram của bạn.

> [!NOTE]
> Để sử dụng tính năng gọi API bên thứ ba này, cả **Real-Debrid** và **TorBox** đều yêu cầu bạn phải sở hữu tài khoản **Trả phí (Premium/Paid Plan)**. Các API Key của tài khoản miễn phí sẽ không được xác thực.

---

## 1. Thiết lập Real-Debrid

Real-Debrid là dịch vụ giải mã link torrent phổ biến nhất hiện nay.

### Lấy API Token:
1. Đăng nhập vào tài khoản Real-Debrid trả phí của bạn.
2. Truy cập đường dẫn: **[https://real-debrid.com/apitoken](https://real-debrid.com/apitoken)**.
3. Tạo và copy chuỗi API Token của bạn.

### Cấu hình file `.env`:
```env
REAL_DEBRID_API_KEY=chuoi_api_token_cua_ban
```

---

## 2. Thiết lập TorBox

TorBox là một dịch vụ Debrid thế hệ mới hỗ trợ API rất mạnh mẽ và tốc độ cao.

### Lấy API Key:
1. Đăng nhập vào tài khoản TorBox trả phí (ví dụ gói Essential hoặc Pro).
2. Truy cập giao diện quản lý hoặc phần cài đặt tài khoản (Account Settings).
3. Copy mã API Key của bạn (thường có dạng Bearer Token).

### Cấu hình file `.env`:
```env
TORBOX_API_KEY=chuoi_api_key_cua_ban
```

---

## 3. Cách thức hoạt động của Luồng Cache & Stream

Khi bạn cấu hình dịch vụ Debrid:

1. **Tìm kiếm & Kiểm tra Cache Tức Thì (Instant Cache Check):**
   Khi bạn tìm kiếm phim trên Stremio, addon sẽ tự động quét các torrent trên mạng công cộng. Sau đó, nó gửi một yêu cầu gộp (batch request) chứa toàn bộ các mã băm (hashes) của các torrent này tới Debrid để kiểm tra xem phim nào đã được người dùng khác tải và cache sẵn trên máy chủ Debrid hay chưa.
   * Nguồn torrent nào có sẵn sẽ hiển thị nhãn: `⚡ [TG Debrid] [Cached]` (Phát ngay lập tức).
   * Nguồn nào chưa có sẵn sẽ hiển thị: `📥 [TG Debrid] [Download]` (Cần tải về).
2. **Xem Không Buffering (302 Redirect):**
   Khi bạn bấm chọn xem phim từ nguồn `⚡ [TG Debrid] [Cached]`, addon sẽ sinh đường dẫn unrestrict từ Debrid và gửi mã phản hồi **HTTP 302 Redirect** đưa trình phát (ExoPlayer, VLC, Web) kết nối thẳng tới hệ thống phân phối nội dung (CDN) tốc độ cao của Debrid. Addon của bạn sẽ **không tốn băng thông** nào để trung chuyển dữ liệu này.
3. **Quy trình Lưu Trữ ngầm lên Telegram (Auto-Cache):**
   Song song với việc chuyển hướng phát video trực tiếp cho bạn xem, một tiến trình nền của addon sẽ tự động tải file phim chất lượng cao đó từ CDN Debrid về ổ đĩa tạm thời của máy chủ và **upload lên Kênh Telegram cá nhân** của bạn. Sau khi upload xong, file tạm sẽ được xóa đi ngay lập tức.
   * Lần tiếp theo bạn tìm phim này, Stremio sẽ tìm thấy trực tiếp từ nguồn lưu trữ Telegram của bạn và phát từ Telegram DC mà không cần gọi API Debrid nữa!
