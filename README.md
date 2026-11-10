# Project-HDH — Trực quan hóa Segmentation

Ứng dụng desktop **Python + Tkinter** minh họa cách dịch địa chỉ logic `(segment_id, offset)` thành địa chỉ vật lý, kiểm tra giới hạn và quyền `r/w/x`. Phần trực quan hóa chạy độc lập ngay trong repository này, dùng thư viện chuẩn Python.

## Chạy chương trình

Cài **Python 3.10 trở lên**, gồm thành phần **Tcl/Tk**. Mở terminal tại thư mục có `run.py`:

```powershell
python run.py
```

Trên Windows có thể nhấp đúp **`Start-Windows.cmd`**. Nếu máy dùng Python Launcher, chạy `py -3 run.py`. Kiểm tra Tkinter bằng `python -m tkinter`; không cần cài gói `tkinter` qua pip.

## Nội dung trực quan hóa

- Bảng segment có `segment_id`, `base`, `limit`, `permissions`; nạp CSV ở tab **Dịch địa chỉ**. Chọn dòng rồi sang tab **Sửa bảng segment** để thêm, sửa hoặc xóa.
- Sơ đồ bốn bước: **tra segment → kiểm tra giới hạn → kiểm tra quyền → cộng base + offset**. Màu sắc thể hiện bước đã qua, lỗi và bước chưa thực hiện.
- Xem từng bước, lùi lại, bắt đầu lại hoặc tự động chạy và tạm dừng.
- Sơ đồ bộ nhớ vật lý và vùng phóng to của segment, có dấu chỉ offset và ranh giới limit.
- Các tình huống mẫu: hợp lệ, địa chỉ cuối segment, offset bằng limit, offset âm, thiếu quyền và segment không tồn tại.
- Dịch danh sách địa chỉ từ CSV, xem giải thích và xuất toàn bộ kết quả kèm trace.

Sơ đồ tổng quan hiển thị tối đa **6 segment**, luôn gồm segment đang dịch nếu tồn tại. Các thanh dùng chung thang địa chỉ; vùng rất nhỏ được vẽ rộng tối thiểu 2 px. Hãy đọc nhãn số hoặc vùng phóng to để xác định địa chỉ. Ô giải thích từng bước có thanh cuộn để đọc toàn bộ nội dung.

`limit` là **độ dài**. Với segment 0 có `base=1000`, `limit=400`, quyền `rx`:

| Yêu cầu | Kết quả |
|---|---|
| `(0, 120)`, đọc `r` | `OK`, địa chỉ vật lý `1120` |
| `(0, 399)`, đọc `r` | `OK`, địa chỉ cuối hợp lệ `1399` |
| `(0, 400)`, đọc `r` | `SEGMENTATION_FAULT` |
| `(0, -1)`, đọc `r` | `SEGMENTATION_FAULT` |
| `(0, 100)`, ghi `w` | `PROTECTION_FAULT` |
| `(9, 10)`, đọc `r` | `SEGMENT_NOT_FOUND` |

Khi có lỗi, mô phỏng dừng tại bước phát hiện lỗi và không sinh địa chỉ vật lý. Kiểm tra giới hạn diễn ra trước kiểm tra quyền.

## Dữ liệu CSV

File đầu vào dùng UTF-8 và dấu phẩy. Các số viết ở hệ thập phân; cột tiêu đề bắt buộc.

```csv
segment_id,base,limit,permissions
0,1000,400,rx
1,2000,300,rw
2,3000,500,rw
```

```csv
segment_id,offset,access
0,120,r
0,400,r
0,100,w
9,10,r
```

`permissions` và `access` là cột tùy chọn; mặc định lần lượt `rw` và `r`. Bảng segment không được trùng ID, chồng lấn hoặc có limit không dương. Offset âm là dữ liệu mô phỏng lỗi hợp lệ; giá trị sai kiểu như `abc` bị từ chối khi đọc CSV. File xuất dùng UTF-8 BOM, thuận tiện mở trong Excel.

## Kiểm thử

```powershell
python -m unittest discover -s tests -v
```

Kiểm thử bao gồm lõi dịch địa chỉ, đọc/xuất CSV, kết quả mẫu và phần trực quan hóa. Kiểm thử GUI cần Tkinter và màn hình khả dụng; môi trường không có màn hình có thể bỏ qua nhóm GUI. GitHub Actions chạy trên Windows với Python 3.10 và 3.14, kiểm tra Tk trước khi chạy toàn bộ bộ test.

## Cấu trúc

```text
run.py                     Điểm chạy ứng dụng
Start-Windows.cmd          Mở ứng dụng trên Windows
src/segmentation.py        Thuật toán và các bước dịch có cấu trúc
src/visualization.py       Thành phần trực quan hóa
src/gui.py                 Giao diện Tkinter
src/csv_io.py              Kiểm tra, đọc và xuất CSV
input/                     Bảng segment, địa chỉ và kết quả kỳ vọng
tests/                     Kiểm thử tự động
report/visualization.md    Thiết kế và kịch bản trình bày
```

Đây là mô hình học tập trên địa chỉ số nguyên, không đọc/ghi bộ nhớ thật. Mô hình xét một không gian địa chỉ với các segment không chồng lấn, không mô phỏng paging hoặc MMU phần cứng. Xem [thiết kế và kịch bản demo](report/visualization.md).
