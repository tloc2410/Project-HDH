#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Khởi chạy ứng dụng với đường dẫn tuyệt đối
if command -v python3 &>/dev/null; then
    python3 "$DIR/run.py"
elif command -v python &>/dev/null; then
    python "$DIR/run.py"
else
    echo "Lỗi: Không tìm thấy Python 3 trên máy Mac của bạn."
    echo "Vui lòng cài đặt Python từ https://www.python.org/downloads/macos/"
    read -p "Nhấn Enter để đóng..."
fi
