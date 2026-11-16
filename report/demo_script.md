# KỊCH BẢN CHẠY VÀ THUYẾT MINH DEMO (DEMO SCRIPT)
## Thành viên 5: Chuẩn bị và chạy demo ứng dụng Segmentation

---

## 1. THÔNG TIN CHUNG VÀ CẤU HÌNH MÁY THỬ NGHIỆM
- **Người thực hiện:** Thành viên 5
- **Môi trường chạy thử nghiệm:**
  - Hệ điều hành: macOS / Windows 10/11 x64
  - Phiên bản Python: Python 3.10 trở lên
  - Giao diện: Tkinter (mặc định) và PySide6
- **Khởi động ứng dụng:**
  - Lệnh terminal: `python run.py` (hoặc `py -3 run.py`)
  - Trên Windows: Nhấp đúp file `Start-Windows.cmd`

---

## 2. BỘ DỮ LIỆU DEMO (3 TÌNH HUỐNG CHUẨN)

Bảng phân đoạn mặc định nạp sẵn trong hệ thống:

| Segment ID | Base Address | Limit (Độ dài) | Permissions (Quyền) |
| :---: | :---: | :---: | :---: |
| **0** | 1000 | 400 | `rx` (Đọc / Thực thi) |
| **1** | 2000 | 300 | `rw` (Đọc / Ghi) |
| **2** | 3000 | 500 | `rw` (Đọc / Ghi) |

---

### Tình huống 1: Dịch địa chỉ thành công (Happy Case)
* **Dữ liệu nhập:**
  - Segment ID = `0`
  - Offset = `120`
  - Thao tác = `r` (Đọc)
* **Kết quả hiển thị trên ứng dụng:**
  - Trạng thái: `OK`
  - Địa chỉ vật lý: `1120`
* **Cách đọc và giải thích Trace:**
  1. *Bước 1 (Tra bảng):* Tìm thấy Segment 0 trong bảng phân đoạn.
  2. *Bước 2 (Kiểm tra giới hạn):* Offset 120 thỏa mãn $0 \le 120 < \text{Limit} (400)$ $\to$ Hợp lệ.
  3. *Bước 3 (Kiểm tra quyền):* Quyền `r` được cho phép trong cấu hình `rx` của Segment 0 $\to$ Hợp lệ.
  4. *Bước 4 (Tính địa chỉ vật lý):* $\text{Physical Address} = \text{Base} + \text{Offset} = 1000 + 120 = 1120$.
  5. *Trực quan hóa RAM:* Vùng nhớ của Segment 0 phát sáng màu xanh, con trỏ đánh dấu đúng ô nhớ 1120.

---

### Tình huống 2: Phân đoạn nằm ngoài bảng (Segment Not Found)
* **Dữ liệu nhập:**
  - Segment ID = `9`
  - Offset = `10`
  - Thao tác = `r` (Đọc)
* **Kết quả hiển thị trên ứng dụng:**
  - Trạng thái: `SEGMENT_NOT_FOUND`
  - Địa chỉ vật lý: `None` (Không tính toán)
* **Cách đọc và giải thích Trace:**
  1. *Bước 1 (Tra bảng):* Hệ thống tra bảng chỉ có các phân đoạn 0, 1, 2; không tìm thấy Segment 9.
  2. *Kích hoạt Bẫy lỗi (Trap):* Quá trình dịch dừng ngay lập tức tại bước tra bảng, xuất thông báo đỏ và không tiếp tục kiểm tra các bước sau.

---

### Tình huống 3: Lỗi vượt giới hạn hoặc Vi phạm quyền truy cập (Faults)

#### 3A. Lỗi tràn Limit (Segmentation Fault):
* **Dữ liệu nhập:**
  - Segment ID = `0`
  - Offset = `400` *(Lỗi biên: độ dài Limit là 400 nên offset chỉ được từ 0 đến 399)*
  - Thao tác = `r`
* **Kết quả:** Báo lỗi `SEGMENTATION_FAULT`.
* **Trace:** Dừng tại Bước 2 (Kiểm tra giới hạn) với thông báo: `offset 400 nằm ngoài [0, 399]`.

#### 3B. Lỗi vi phạm quyền bảo vệ (Protection Fault):
* **Dữ liệu nhập:**
  - Segment ID = `0`
  - Offset = `100`
  - Thao tác = `w` (Cố tình Ghi dữ liệu)
* **Kết quả:** Báo lỗi `PROTECTION_FAULT`.
* **Trace:** Bước 1 và Bước 2 hợp lệ, nhưng dừng tại Bước 3 (Kiểm tra quyền) với thông báo: `Segment 0 có quyền rx, không cho phép thao tác w`.

---

## 3. KỊCH BẢN NÓI KHI QUAY VIDEO DEMO (3 – 5 PHÚT)

1. **Phần mở đầu (00:00 - 00:30):**
   - Giới thiệu bản thân, tên đề tài "Mô phỏng phân đoạn bộ nhớ và dịch địa chỉ logic".
   - Mở ứng dụng bằng lệnh `python run.py` (hoặc nhấp `Start-Windows.cmd`).
2. **Demo Tình huống 1: Dịch hợp lệ (00:30 - 01:30):**
   - Nhập $s=0, d=120$, chọn `r`.
   - Bấm nút "Từng bước" (Next Step) để minh họa hoạt họa luồng dịch 4 bước.
   - Chỉ vào sơ đồ thanh RAM đang highlight vùng nhớ 1120.
3. **Demo Tình huống 2: Phân đoạn ngoài bảng (01:30 - 02:30):**
   - Nhập $s=9, d=10$.
   - Bấm "Dịch địa chỉ" $\to$ chỉ vào lỗi `SEGMENT_NOT_FOUND` dừng ở bước 1.
4. **Demo Tình huống 3: Lỗi biên & Vi phạm quyền (02:30 - 03:30):**
   - Nhập $s=0, d=400 \to$ kích hoạt bẫy lỗi `SEGMENTATION_FAULT`.
   - Nhập $s=0, d=100$, chọn `w` $\to$ kích hoạt bẫy lỗi `PROTECTION_FAULT`.
5. **Demo Nạp dữ liệu hàng loạt từ CSV (03:30 - 04:30):**
   - Chuyển sang tab nạp CSV, chọn `input/addresses.csv`.
   - Bấm dịch toàn bộ và bấm "Xuất kết quả CSV" để chứng minh tính tái lập kết quả.
6. **Tổng kết (04:30 - 05:00):**
   - Tóm tắt kết quả demo, xác nhận ứng dụng chạy mượt mà, không crash khi gặp lỗi.

---

## 4. GHI NHẬN KIỂM THỬ VÀ LỖI KHI CÀI ĐẶT
- Chạy thử nghiệm thành công trên cả macOS (Apple Silicon) và Windows x64.
- Cài đặt không yêu cầu thư viện bên ngoài đối với bản Tkinter; bản PySide6 chỉ cần chạy `pip install -r requirements-qt.txt`.
- Không phát sinh lỗi crash khi nhập ký tự lạ hoặc dữ liệu rỗng.
