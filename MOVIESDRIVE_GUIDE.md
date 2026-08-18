# 🎬 MoviesDrive Cinema - Stremio Addon (4K UHD & Dual Audio)

Addon **MoviesDrive** cho phép tìm kiếm và xem phim bom tấn Hollywood, Bollywood, Netflix, Disney+, Amazon Prime chất lượng cao **4K UHD (2160p), 1080p FHD, 720p HD**, hỗ trợ **Dual Audio (Hindi + English / Original)** và phát trực tuyến tốc độ cao 10Gbps (Cloudflare Workers / Google CDN) trên mọi thiết bị Stremio.

---

## ✨ Tính năng nổi bật của MoviesDrive Addon

1. **Chất lượng Video Đỉnh cao (4K UHD, 1080p, 720p)**:
   - Kho phim 4K UHD 2160p (HDR / DV / SDR) phong phú.
   - Hỗ trợ đa âm thanh: Dual Audio (Hindi Org + English Org) và phụ đề ESub.

2. **Phát Trực Tiếp Tốc độ cao 10Gbps**:
   - Sủ dụng máy chủ phân phối Cloudflare Workers / Pixel / Google CDN.
   - Tích hợp Proxy stream hỗ trợ đầy đủ **HTTP Range 206 Partial Content** giúp tua / seek / scrub nhanh không bị giật lag trên Stremio (LibVLC / ExoPlayer).

3. **Hỗ trợ Mã IMDb (Cinemeta `tt...`) & Tìm kiếm Thông minh**:
   - Bạn có thể duyệt phim từ Catalogs của MoviesDrive.
   - Hoặc khi bạn bấm vào bất kỳ phim nào trong thư viện / bảng xếp hạng mặc định của Stremio, addon sẽ tự động tìm kiếm và hiển thị nguồn stream từ MoviesDrive.

4. **Danh mục Khám phá (Discover) Đa dạng**:
   - **MoviesDrive - Phim Mới**: Cập nhật phim chiếu rạp và web series hot nhất.
   - **MoviesDrive - Phim 4K UHD**: Danh mục dành riêng cho các tín đồ xem phim màn hình lớn 4K.
   - **MoviesDrive - Phim Bộ (Series)**: Hỗ trợ phim bộ nhiều mùa (Seasons) và tập (Episodes).
   - **26 Thể loại chọn lọc**: Action, Adventure, Animation, Anime, Bollywood, Comedy, Crime, Documentary, Drama, Dual Audio, DV HDR, Family, Fantasy, Hindi Dubbed, Hollywood, Horror, IMAX, K-Drama, Mystery, Netflix, Romance, Sci-Fi, South, Thriller, War, 2160p 4K.

5. **Tự chọn tên miền sống (mới)**:
   - MoviesDrive đổi tên miền liên tục, nên addon tự dò mirror, ghim mirror đang sống, cho mirror lỗi "nghỉ" một lúc, và nhận ra trang chặn của Cloudflare thay vì tưởng là tải thành công.
   - Toàn bộ tên miền, selector và đường dẩn đều đặt được bằng biến môi trường `MD_*` (xem `.env.example`), không cần sửa code.

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

### 2. Đường dẩn Manifest URL (Stremio)

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
3. Dán đường dẩn Manifest URL ở trên vào và nhấn **Install**.
4. Chuyển sang mục **Discover (Khám phá)** ➔ Chọn nguồn **MoviesDrive** để bắt đầu thưởng thức phim 4K!

---

## 🩺 Khắc phục sự cố: MoviesDrive không tải được dữ liệu

### Bước 0. Xem trạng thái thực tế

```text
GET http://127.0.0.1:7000/moviesdrive/cache_stats
```

Các trường quan trọng:

| Trường | Ý nghĩa |
| --- | --- |
| `active_base` | Tên miền đang được dùng thật sự |
| `env_base` | Giá trị `MD_BASE_URL` bạn đặt (rỗng = đang dùng mặc định trong code) |
| `known_bases` | Toàn bộ mirror addon biết |
| `cooling_bases` | Mirror đang bị cho nghỉ vì lỗi liên tục |
| `base_failures` | Số lần lỗi của từng mirror |
| `antibot` | Các cơ chế vượt chặn đang khả dụng |
| `fresh` / `stale` | Số bản ghi cache còn hạn / đã hết hạn |

`fresh = 0` sau khi đã mở Discover một lúc nghĩa là không scrape được gì cả.

### Trường hợp 1 - Tên miền đã chết (phổ biến nhất)

Dấu hiệu: log báo `HTTP 403/404/522` hoặc timeout cho mọi mirror.

Kiểm tra nhanh bằng tay:

```bash
curl -I https://new2.moviesdrive.christmas
```

Sửa:

```env
MD_BASE_URL=https://ten-mien-dang-song
MD_MIRRORS=https://mirror-1,https://mirror-2
# Hoặc để addon tự sinh và tự dò:
MD_MIRROR_TEMPLATES=https://new{n}.moviesdrive.christmas
MD_MIRROR_RANGE=1-8
```

Rồi restart addon. Addon sẽ tự dò lại (`MD_BASE_DISCOVERY_TTL`) khi mirror đang ghim chết.

### Trường hợp 2 - Bị Cloudflare chặn

Dấu hiệu: log báo đã loại bỏ body vì `looks_blocked`, hoặc HTTP 403/503 liên tục dù mở trên trình duyệt vẫn vào được.

```env
MD_ANTIBOT_FALLBACK=true
MD_IMPERSONATE=chrome120          # cần: pip install curl_cffi
MD_FLARESOLVERR_URL=http://localhost:8191/v1   # nếu bạn chạy FlareSolverr
```

Nếu không cài `curl_cffi` và không chạy FlareSolverr thì addon chỉ bỏ qua bước này, không báo lỗi.

### Trường hợp 3 - Web đổi layout

Dấu hiệu: tên miền sống nhưng log báo `parsed 0 cards`, hoặc catalog rỗng / không còn nút tải.

```env
# Thẻ phim đổi class
MD_CARD_SELECTORS=div.new-card,article.post
MD_LINK_SELECTORS=h2.entry-title a[href]
# Đổi slug chuyên mục
MD_CATEGORY_MOVIES=movies
MD_CATEGORY_SERIES=web-series
MD_CATEGORY_4K=4k
MD_GENRE_MAP={"Sci-Fi": "sci-fi", "Thriller": "thriller"}
# Đổi đường dẩn tìm kiếm (JSON trước, không được thì tự sang trang HTML)
MD_SEARCH_PATH=/search.php?q={query}&page={page}
MD_SEARCH_HTML_PATH=/page/{page}/?s={query}
```

### Trường hợp 4 - Ra danh sách phim nhưng bấm Play lỗi 502

Tầng giải link HubCloud / GamerXYT đã đổi. Log sẽ nói rõ hỏng ở bước nào
(không thấy token, không thấy link gamerxyt, không thấy link CDN).

```env
MD_HUBCLOUD_BASE=https://hubcloud.xx
MD_GAMERXYT_BASE=https://ten-mien-moi
MD_DIRECT_HOSTS=cdn-moi.example.com
```

### Trường hợp 5 - Cuộn Discover bị trùng / thiếu phim

Addon tự học số phim mỗi trang từ trang 1. Nếu vẫn lệch, đặt đúng số đếm được
trên web:

```env
MD_ITEMS_PER_PAGE=24
MD_CATALOG_PAGE_SIZE=20
```

### Mẹo chung

* Poster / điểm IMDb hiện chậm ở lần đầu: tăng `MD_META_ENRICH_TIMEOUT`.
* Muốn thấy lý do lỗi ngay trong Stremio: giữ `MD_SHOW_ERRORS=true` (mặc định).
  Đặt `false` nếu bạn muốn danh sách trống như cũ.
* Sau khi đổi biến môi trường, nên xoá file cache (`MD_CACHE_FILE`) để không
  dùng lại kết quả rỗng đã nhớ trước đó.
* Toan bộ danh sách biến `MD_*` kèm giải thích: xem `.env.example`.
