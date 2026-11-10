# Phần trực quan hóa Segmentation

## Mục đích

Minh họa việc kiểm tra và dịch địa chỉ logic `(segment_id, offset)` thành địa chỉ vật lý. Người xem theo dõi được vì sao yêu cầu hợp lệ hoặc bị từ chối, thay vì chỉ nhận một con số kết quả.

Ứng dụng desktop dùng Python + Tkinter và chạy độc lập trong `Project-HDH` bằng `python run.py`.

## Luồng bốn bước

| Bước | Điều kiện/Phép tính | Nếu không đạt |
|---|---|---|
| Tra segment | Tìm ID trong bảng segment | `SEGMENT_NOT_FOUND` |
| Kiểm tra giới hạn | `0 <= offset < limit` | `SEGMENTATION_FAULT` |
| Kiểm tra quyền | Thao tác `r`, `w` hoặc `x` nằm trong quyền segment | `PROTECTION_FAULT` |
| Dịch địa chỉ | `physical_address = base + offset` | Chỉ thực hiện sau ba bước trên |

Các bước lấy từ kết quả có cấu trúc của lõi thuật toán. Phần vẽ không tự suy đoán kết quả từ nội dung chuỗi trace. Lỗi dừng luồng xử lý ngay; các bước phía sau không được đánh dấu thành công.

Người dùng có thể tiến, lùi, bắt đầu lại, tự động chạy và tạm dừng. Kết quả cuối cùng và dấu địa chỉ vật lý chỉ xuất hiện khi đi đến bước dịch thành công.

## Cách đọc sơ đồ

Bảng segment hiển thị ID, base, limit và quyền `r/w/x`. Sơ đồ tổng quan cho biết các vùng segment nằm ở đâu trong không gian địa chỉ vật lý. Vùng phóng to tập trung vào segment được truy cập để nhìn rõ offset và ranh giới limit, kể cả khi segment quá nhỏ trên sơ đồ tổng quan.

Sơ đồ hiển thị tối đa 6 segment và luôn giữ segment đang dịch nếu tìm thấy. Các vùng dùng chung thang địa chỉ; vùng rất nhỏ được vẽ rộng tối thiểu 2 px, vì vậy giá trị số là căn cứ xác định địa chỉ chính xác. Ô giải thích có thanh cuộn để đọc toàn bộ các bước.

`limit` là độ dài; segment có base 1000 và limit 400 chiếm địa chỉ từ 1000 đến 1399. Offset 399 trỏ đến ô cuối hợp lệ. Offset 400 nằm ngoài segment. Dấu đánh lỗi ngoài biên chỉ minh họa yêu cầu bị từ chối, không phải một địa chỉ vật lý đã được dịch.

## Kịch bản demo

1. Mở ứng dụng và nạp bảng mẫu gồm segment 0 `(1000,400,rx)`, segment 1 `(2000,300,rw)`, segment 2 `(3000,500,rw)`.
2. Chọn tình huống hợp lệ `(0,120,r)`. Đi từng bước: tìm segment 0; xác nhận `0 <= 120 < 400`; quyền đọc có trong `rx`; tính `1000 + 120 = 1120`. Quan sát vị trí trên sơ đồ.
3. Thử `(0,399,r)` để chỉ ra địa chỉ cuối hợp lệ là 1399.
4. Thử `(0,400,r)` và `(0,-1,r)`. Luồng dừng tại kiểm tra giới hạn, không tính địa chỉ vật lý.
5. Thử `(0,100,w)`. Kiểm tra giới hạn thành công nhưng kiểm tra quyền thất bại vì `rx` không có `w`.
6. Thử `(9,10,r)`. Lỗi xuất hiện ngay tại tra segment; các bước sau không thực hiện.
7. Dùng chế độ tự động, tạm dừng và lùi một bước để giải thích lại điều kiện. Chọn dòng trong bảng ở tab **Dịch địa chỉ**, sang tab **Sửa bảng segment**, sửa thông số rồi bấm **Thêm / cập nhật**. Quay lại dịch địa chỉ để thấy kết quả dùng bảng mới. Nút **Xóa segment chọn** ở tab sửa dùng dòng đã chọn trong bảng.
8. Sang xử lý CSV, chạy `input/addresses.csv`, chọn một dòng để xem trace và xuất kết quả. Đối chiếu với `input/expected_results.csv`.

## Tách trách nhiệm

`src/segmentation.py` kiểm tra dữ liệu, tra bảng và tạo kết quả cùng các bước xử lý. `src/visualization.py` chịu trách nhiệm biểu diễn quá trình. `src/gui.py` nối thao tác người dùng với lõi và cập nhật cửa sổ. `src/csv_io.py` xử lý tệp; lỗi định dạng CSV được phân biệt với lỗi mô phỏng.

Kiểm thử chạy bằng `python -m unittest discover -s tests -v`. Kết quả mẫu được tính trước trong `input/expected_results.csv`; kiểm thử đối chiếu trạng thái và địa chỉ vật lý. Bộ test GUI cần Tkinter với màn hình khả dụng.

## Giới hạn mô hình

Mỗi yêu cầu truy cập một địa chỉ số nguyên. Các segment tăng theo chiều dương, không chồng lấn trong một không gian địa chỉ. Quyền `r/w/x` dùng để minh họa bảo vệ. Chương trình không truy cập bộ nhớ thật, không mô phỏng paging, TLB, cấp phát động, stack tăng xuống hoặc nhiều tiến trình.
