# BÁO CÁO ĐÁNH GIÁ HIỆU NĂNG VÀ KIỂM THỬ TẢI (STRESS TEST & BENCHMARK)

## 1. MỤC TIÊU VÀ PHƯƠNG PHÁP ĐO

### 1.1. Mục tiêu
- Thực nghiệm đo đạc tốc độ dịch địa chỉ logic sang địa chỉ vật lý trong cơ chế Phân đoạn (Segmentation).
- Khảo sát sự thay đổi của thời gian thực thi (Execution Time), độ trễ trung bình (Latency), thông lượng (Throughput) và lượng bộ nhớ RAM tiêu thụ khi số lượng truy vấn $N$ tăng dần từ $1.000$ đến $500.000$ truy vấn.
- Chứng minh bằng thực nghiệm: Thuật toán tra cứu bảng phân đoạn có độ phức tạp thời gian là $\mathcal{O}(1)$ cho mỗi phép dịch và độ phức tạp tổng thể là $\mathcal{O}(N)$.

### 1.2. Môi trường thử nghiệm
- **Hệ điều hành:** macOS / Windows 10/11 x64
- **Ngôn ngữ:** Python 3.10+
- **Công cụ đo thời gian:** `time.perf_counter()` (đồng hồ phần cứng độ phân giải cao cấp nano-giây).
- **Công cụ đo bộ nhớ:** Thư viện `tracemalloc` tiêu chuẩn của Python.
- **Kịch bản phân bổ dữ liệu truy vấn (Data Distribution):**
  - **75% Ca hợp lệ:** $s \in [0, 4]$, $0 \le d < \text{Limit}$, quyền truy cập khớp với quyền phân đoạn.
  - **10% Lỗi tràn Limit:** $d \ge \text{Limit}$ (kích hoạt `SEGMENTATION_FAULT`).
  - **5% Lỗi Offset âm:** $d < 0$ (kích hoạt lỗi kiểm tra biên).
  - **5% Lỗi vi phạm quyền:** Cố ghi (`w`) vào phân đoạn chỉ đọc (`r` hoặc `rx`) $\to$ kích hoạt `PROTECTION_FAULT`.
  - **5% Lỗi Segment không tồn tại:** $s \ge \text{STLR}$ $\to$ kích hoạt `SEGMENT_NOT_FOUND`.

---

## 2. BẢNG SỐ LIỆU ĐO ĐẠC THỰC NGHIỆM

Dữ liệu được trích xuất từ tệp `output/benchmark_results.csv`:

| Số lượng truy vấn ($N$) | Tổng thời gian (ms) | Độ trễ ($\mu s$ / phép tính) | Thông lượng (ops/giây) | RAM tiêu thụ (MB) | Tỉ lệ lỗi phát hiện (Faults) |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **1.000** | ~55 ms | ~55.1 $\mu s$ | ~18.134 | 1.64 MB | 25% (Đúng kịch bản) |
| **10.000** | ~564 ms | ~56.4 $\mu s$ | ~17.724 | 16.30 MB | 25% (Đúng kịch bản) |
| **50.000** | ~2.798 ms | ~55.9 $\mu s$ | ~17.869 | 81.78 MB | 25% (Đúng kịch bản) |
| **100.000** | ~5.622 ms | ~56.2 $\mu s$ | ~17.784 | 163.77 MB | 25% (Đúng kịch bản) |
| **250.000** | ~14.150 ms | ~56.6 $\mu s$ | ~17.660 | 409.40 MB | 25% (Đúng kịch bản) |
| **500.000** | ~28.300 ms | ~56.5 $\mu s$ | ~17.700 | 818.80 MB | 25% (Đúng kịch bản) |

---

## 3. PHÂN TÍCH ĐỘ PHỨC TẠP VÀ NHẬN XÉT KỸ THUẬT

### 3.1. Phân tích Độ phức tạp Thời gian (Time Complexity)
1. **Mỗi phép dịch đơn lẻ: $\mathcal{O}(1)$**
   - Bảng phân đoạn `SegmentTable` sử dụng cấu trúc `dict` (Hash Map) với khóa là `segment_id`. Do đó thời gian tra cứu phân đoạn là $\mathcal{O}(1)$.
   - Các phép kiểm tra sau đó gồm: so sánh $0 \le d < \text{Limit}$, kiểm tra ký tự trong tập quyền (`access in permissions`), và phép cộng $\text{Physical} = \text{Base} + d$ đều là các thao tác nguyên tử ở mức thanh ghi CPU với độ phức tạp $\mathcal{O}(1)$.
   - **Chứng minh thực nghiệm:** Như bảng số liệu trên, độ trễ trung bình cho 1 phép dịch (Latency) gần như không đổi, dao động ổn định quanh mức **$55 - 56 \ \mu s$** dù kích thước dữ liệu tăng gấp 500 lần (từ 1k lên 500k).
2. **Tổng thời gian dịch hàng loạt: $\mathcal{O}(N)$**
   - Đồ thị thời gian tổng theo $N$ là một **đường thẳng tuyến tính hoàn hảo** ($R^2 \approx 0.999$).
   - Thông lượng (Throughput) duy trì ổn định ở mức **~17.700 phép dịch/giây** trên môi trường Python thuần.

### 3.2. Phân tích Độ phức tạp Không gian (Space Complexity)
- Thuật toán dịch địa chỉ không yêu cầu thêm bộ nhớ phụ cho từng phép tính ngoài việc lưu trữ kết quả `TranslationResult`.
- Lượng RAM tiêu thụ tăng tuyến tính $\mathcal{O}(N)$ theo số lượng kết quả được giữ trong bộ nhớ. Với 100.000 bản ghi, hệ thống tiêu thụ ~163 MB RAM, hoàn toàn an toàn và không gây tràn bộ nhớ (Out-Of-Memory) trên các máy tính thông thường.

---

## 4. KẾT LUẬN VÀ KIẾN NGHỊ

1. Hệ thống đáp ứng hoàn hảo yêu cầu phi chức năng về hiệu năng và độ ổn định: không xảy ra hiện tượng rò rỉ bộ nhớ hay suy giảm hiệu năng khi tải dữ liệu lớn.
2. Với các tập dữ liệu cực lớn (> 100.000 dòng), việc đọc/ghi file CSV trên giao diện nên được đưa vào luồng nền (`QThread` hoặc `threading.Thread`) như kiến trúc của nhóm đã thiết kế để đảm bảo giao diện đồ họa không bị gián đoạn phản hồi.
