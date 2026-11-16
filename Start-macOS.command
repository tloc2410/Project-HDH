#!/bin/bash
cd "$(dirname "$0")"

# Kiểm tra và khởi chạy ứng dụng bằng Python 3
if command -v python3 &>/dev/null; then
    python3 run.py
elif command -v python &>/dev/null; then
    python run.py
else
    echo "Lỗi: Không tìm thấy Python 3 trên máy Mac của bạn."
    echo "Vui lòng cài đặt Python từ https://www.python.org/downloads/macos/"
    read -p "Nhấn phím Enter để đóng cửa sổ..."
fi
