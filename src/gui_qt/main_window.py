from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QScrollArea,
    QStackedWidget, QVBoxLayout, QWidget,
)

from .dashboard import Dashboard, btn, card, fill_history, make_history_table
from .styles import STYLE


class CsvPage(QWidget):
    load_segments_requested = Signal()
    translate_csv_requested = Signal()
    export_requested = Signal()

    def __init__(self):
        super().__init__()
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        frame, layout = card('Nhập / Xuất CSV')
        guidance = QLabel(
            'Nạp CSV bảng phân đoạn hoặc dịch danh sách địa chỉ bằng bảng hiện tại. '
            'Tệp xuất chứa kết quả dịch hàng loạt gần nhất.'
        )
        guidance.setWordWrap(True)
        layout.addWidget(guidance)

        actions = QHBoxLayout()
        actions.addWidget(btn('Nạp bảng phân đoạn', lambda: self.load_segments_requested.emit(), 'secondary'))
        actions.addWidget(btn('Dịch danh sách địa chỉ', lambda: self.translate_csv_requested.emit(), 'primary'))
        self.export_button = btn('Xuất kết quả', lambda: self.export_requested.emit(), 'secondary')
        self.set_export_enabled(False)
        actions.addWidget(self.export_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.status = QLabel('Chọn tệp CSV để bắt đầu.')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setObjectName('infoBox')
        layout.addWidget(self.status)
        layout.addStretch()
        page_layout.addWidget(frame)

    def set_status(self, message):
        self.status.setText(str(message))

    def set_export_enabled(self, enabled):
        self.export_button.setEnabled(enabled)


class MainWindow(QMainWindow):
    """Cửa sổ và điều hướng của giao diện PySide6."""
    reset_requested = Signal()
    csv_page_requested = Signal()
    history_page_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Segmentation Simulator | Mô phỏng địa chỉ logic')
        self.resize(1420, 870)
        self.setMinimumSize(1000, 650)
        self.setStyleSheet(STYLE)
        root = QWidget()
        root.setObjectName('root')
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(220)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(15, 25, 15, 18)
        sl.setSpacing(10)
        brand = QLabel('▣  Segmentation\n     Simulator')
        brand.setObjectName('brand')
        sl.addWidget(brand)
        sl.addSpacing(27)
        self.nav = []
        for i, label in enumerate(['⌂  Trang chủ', '◷  Lịch sử', '▤  Nhập / Xuất CSV', 'ⓘ  Hướng dẫn']):
            b = QPushButton(label)
            b.setObjectName('nav')
            b.clicked.connect(lambda checked=False, idx=i: self.show_page(idx))
            sl.addWidget(b)
            self.nav.append(b)
        sl.addStretch()
        info = QLabel('Mô phỏng phân đoạn bộ nhớ\nvà chuyển đổi địa chỉ logic\nsang địa chỉ vật lý.')
        info.setObjectName('sideInfo')
        info.setWordWrap(True)
        sl.addWidget(info)
        outer.addWidget(sidebar)

        self.scroll = QScrollArea()
        self.scroll.setObjectName('pageScroll')
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self.scroll, 1)
        content = QWidget()
        content.setObjectName('pageContent')
        self.scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(22, 25, 22, 23)
        layout.setSpacing(15)
        top = QHBoxLayout()
        title = QLabel('Mô phỏng Segmentation và Địa chỉ Logic')
        title.setObjectName('title')
        top.addWidget(title, 1)
        reset = QPushButton('↻  Đặt lại')
        reset.setObjectName('secondary')
        reset.clicked.connect(lambda: self.reset_requested.emit())
        top.addWidget(reset)
        layout.addLayout(top)

        self.pages = QStackedWidget()
        self.dashboard = Dashboard()
        self.pages.addWidget(self.dashboard)
        history_page, history_layout = card('Lịch sử dịch địa chỉ')
        self.history_table = make_history_table()
        history_layout.addWidget(self.history_table)
        self.pages.addWidget(history_page)
        self.csv_page = CsvPage()
        self.pages.addWidget(self.csv_page)
        self.pages.addWidget(self._help_page())
        layout.addWidget(self.pages, 1)
        self.show_page(0)

    def _help_page(self):
        page, layout = card('Hướng dẫn sử dụng')
        message = QLabel(
            '1. Kiểm tra bảng phân đoạn hoặc nạp bảng mới từ trang CSV.\n'
            '2. Nhập Segment, Offset và chọn thao tác đọc, ghi hoặc thực thi.\n'
            '3. Chọn Dịch địa chỉ để xem kết quả ngay hoặc chọn Từng bước rồi bấm Bước tiếp.\n'
            '4. Xem địa chỉ vật lý và vị trí trong sơ đồ bộ nhớ khi phép dịch thành công.\n\n'
            'Offset hợp lệ khi 0 ≤ Offset < Limit. Thao tác cần có quyền tương ứng trên phân đoạn.\n'
            'CSV bảng phân đoạn dùng các cột segment_id, base, limit, permissions.\n'
            'CSV địa chỉ dùng các cột segment_id, offset, access.'
        )
        message.setWordWrap(True)
        layout.addWidget(message)
        layout.addStretch()
        return page

    def set_history(self, records):
        fill_history(self.history_table, records)

    def show_page(self, index):
        self.pages.setCurrentIndex(index)
        self.scroll.verticalScrollBar().setValue(0)
        for i, b in enumerate(self.nav):
            b.setProperty('active', 'true' if i == index else 'false')
            b.style().unpolish(b)
            b.style().polish(b)
        if index == 1:
            self.history_page_requested.emit()
        elif index == 2:
            self.csv_page_requested.emit()
