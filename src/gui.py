import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QGridLayout, QHeaderView, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)

from .segmentation import LogicalAddress, Segment, SegmentTable
from .csv_io import load_addresses, load_segments, save_results
from .visualization import Playback, PALETTE, STAGES, compact


STYLE = '''
QWidget {font-family: 'Segoe UI', Arial; font-size: 12px; color: #142b50;}
QWidget#root {background: #f1f5fb;}
QFrame#sidebar {background: #172f54; border: none;}
QLabel#brand {color: white; font-size: 17px; font-weight: 800;}
QLabel#sideInfo {color: #c3d6f3; font-size: 11px;}
QPushButton#nav {text-align: left; background: transparent; color: #d9e7ff; border: none; padding: 12px 14px; border-radius: 8px; font-weight: 600;}
QPushButton#nav:hover {background: #284873;}
QPushButton#nav[active="true"] {background: #2c74f4; color: white;}
QLabel#title {font-size: 23px; font-weight: 800; color: #142b50;}
QLabel#muted {color: #7385a4; font-size: 11px;}
QLabel#section {font-size: 15px; font-weight: 750;}
QFrame#card {background: white; border: 1px solid #dfe8f5; border-radius: 13px;}
QPushButton {background: white; border: 1px solid #cbd9ef; padding: 9px 12px; border-radius: 7px; font-weight: 600;}
QPushButton:hover {background: #eaf2ff;}
QPushButton#primary {background: #2b73f4; color: white; border-color: #2b73f4;}
QPushButton#primary:hover {background: #155ddd;}
QPushButton#secondary {background: #edf4ff; color: #245fc2; border-color: #d9e6fa;}
QPushButton#danger {background: #fff0f2; color: #bb3543; border-color: #f4cbd0;}
QLineEdit, QComboBox {background: white; border: 1px solid #ccd9eb; border-radius: 6px; padding: 8px; min-height: 20px;}
QTableWidget {background: white; border: 1px solid #e0e9f6; gridline-color: #e5ecf6; selection-background-color: #d8e8ff; alternate-background-color: #f8faff;}
QHeaderView::section {background: #f0f5fc; border: none; border-bottom: 1px solid #e1e9f4; padding: 9px; font-weight: bold;}
QLabel#infoBox {background: #edf4ff; color: #5373a3; border-radius: 8px; padding: 13px;}
QFrame#placeholder {background: #f1f5fb; border: 1px dashed #d4e2f5; border-radius: 8px;}
'''


def button(label, callback, role='secondary'):
    widget = QPushButton(label)
    widget.setObjectName(role)
    widget.clicked.connect(callback)
    return widget


def card(title):
    frame = QFrame()
    frame.setObjectName('card')
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 15, 16, 15)
    layout.setSpacing(11)
    heading = QLabel(title)
    heading.setObjectName('section')
    layout.addWidget(heading)
    return frame, layout


def data_table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    widget.verticalHeader().hide()
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    widget.setAlternatingRowColors(True)
    return widget


def display_permissions(value):
    return ''.join(char if char in value else '-' for char in 'rwx')


class SegmentDialog(QDialog):
    def __init__(self, parent=None, segment=None):
        super().__init__(parent)
        self.setWindowTitle('Sửa phân đoạn' if segment else 'Thêm phân đoạn')
        self.setMinimumWidth(370)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.segment_id = QLineEdit()
        self.base = QLineEdit()
        self.limit = QLineEdit()
        self.permission = QComboBox()
        for text, code in (
            ('r--', 'r'), ('rw-', 'rw'), ('r-x', 'rx'), ('rwx', 'rwx'),
            ('-w-', 'w'), ('--x', 'x'), ('-wx', 'wx')
        ):
            self.permission.addItem(text, code)
        if segment is not None:
            self.segment_id.setText(str(segment.segment_id))
            self.segment_id.setReadOnly(True)
            self.base.setText(str(segment.base))
            self.limit.setText(str(segment.limit))
            self.permission.setCurrentText(display_permissions(segment.permissions))
        form.addRow('Segment ID:', self.segment_id)
        form.addRow('Base:', self.base)
        form.addRow('Limit:', self.limit)
        form.addRow('Quyền:', self.permission)
        root.addLayout(form)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        controls.button(QDialogButtonBox.StandardButton.Save).setText('Lưu')
        controls.button(QDialogButtonBox.StandardButton.Cancel).setText('Hủy')
        controls.accepted.connect(self.accept)
        controls.rejected.connect(self.reject)
        root.addWidget(controls)

    def get_segment(self):
        return Segment(
            segment_id=int(self.segment_id.text().strip()),
            base=int(self.base.text().strip()),
            limit=int(self.limit.text().strip()),
            permissions=self.permission.currentData()
        )


class PipelineWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.labels = []
        for index, (_, title) in enumerate(STAGES):
            label = QLabel(f'{index + 1}. {title}\nChưa chạy')
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            label.setMinimumHeight(62)
            layout.addWidget(label, 1)
            self.labels.append(label)
        self.set_playback(Playback())

    def set_playback(self, playback):
        states = {'pass': 'Đạt', 'error': 'Lỗi · dừng', 'waiting': 'Chưa chạy', 'skipped': 'Bỏ qua'}
        for index, (label, stage) in enumerate(zip(self.labels, playback.stages())):
            label.setText(f'{index + 1}. {stage.title}\n{states[stage.state]}')
            background = PALETTE[stage.state + '_bg']
            foreground = PALETTE[stage.state]
            label.setStyleSheet(
                f'background:{background};color:{foreground};border:1px solid {foreground};'
                'border-radius:7px;padding:5px;font-size:10px;font-weight:600;'
            )


class MemoryMapWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.table = None
        self.playback = Playback()
        self.setMinimumHeight(230)

    def set_state(self, table, playback):
        self.table = table
        self.playback = playback
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor('white'))
        painter.setFont(QFont('Segoe UI', 9))
        width, height = self.width(), self.height()
        if self.table is None:
            painter.setPen(QColor(PALETTE['muted']))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             'Thêm hoặc nhập bảng phân đoạn để xem Memory Map')
            return
        segments = list(self.table.segments[:6])
        maximum = max(segment.base + segment.limit for segment in self.table.segments)
        result = self.playback.result
        looked_up = result is not None and self.playback.visible > 0
        selected = next((segment for segment in self.table.segments
                         if looked_up and segment.segment_id == result.segment_id), None)
        if selected is not None and selected not in segments:
            segments[-1] = selected
        failed = bool(result and self.playback.complete and result.status != 'OK')
        left, right = 76.0, float(max(width - 28, 130))
        span = right - left
        painter.setPen(QColor(PALETTE['text']))
        painter.drawText(3, 17, 'BỘ NHỚ VẬT LÝ · thang địa chỉ chung')
        painter.setPen(QPen(QColor(PALETTE['line']), 1))
        painter.drawLine(int(left), 36, int(right), 36)
        painter.setPen(QColor(PALETTE['muted']))
        painter.drawText(int(left), 29, '0')
        painter.drawText(QRectF(right - 110, 19, 110, 18), Qt.AlignmentFlag.AlignRight,
                         compact(maximum - 1))
        region_height = max(100, height - 115)
        row_height = min(27, max(17, (region_height - 25) / max(len(segments), 1)))
        for index, segment in enumerate(segments):
            y = 47 + index * row_height
            active = selected is segment
            fill = PALETTE['error'] if active and failed else PALETTE['pass'] if active else '#b6cbdc'
            x0 = min(right - 2, left + segment.base / maximum * span)
            x1 = max(x0 + 2, left + (segment.base + segment.limit) / maximum * span)
            painter.setPen(QColor(PALETTE['text']))
            painter.drawText(2, int(y + 11), f'S{compact(segment.segment_id, 9)}')
            painter.fillRect(QRectF(x0, y, max(2, x1 - x0), 12), QColor(fill))
            if active and self.playback.physical_address is not None:
                marker = left + self.playback.physical_address / maximum * span
                painter.setPen(QPen(QColor(PALETTE['text']), 2))
                painter.drawLine(int(marker), int(y - 4), int(marker), int(y + 17))
        zoom_y = max(155, height - 88)
        if selected is None:
            message = 'Nhấn Từng bước để theo dõi segment và offset.'
            if looked_up:
                message = f'Không tìm thấy segment {result.segment_id}.'
            painter.setPen(QColor(PALETTE['muted']))
            painter.drawText(QRectF(5, zoom_y, width - 10, 50),
                             Qt.AlignmentFlag.AlignCenter, message)
        else:
            painter.setPen(QColor(PALETTE['text']))
            painter.drawText(3, zoom_y,
                             f'PHÓNG TO S{compact(selected.segment_id)} · base {compact(selected.base)} · quyền {selected.permissions}')
            bar_y = zoom_y + 10
            painter.setPen(QPen(QColor(PALETTE['pass']), 1))
            painter.setBrush(QColor(PALETTE['pass_bg']))
            painter.drawRect(QRectF(left, bar_y, span, 16))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor(PALETTE['muted']))
            painter.drawText(int(left), int(bar_y + 30), 'offset 0')
            painter.drawText(QRectF(right - 150, bar_y + 17, 150, 18),
                             Qt.AlignmentFlag.AlignRight,
                             f'limit {compact(selected.limit)} (loại trừ)')
            if result is not None and any(step.stage == 'bounds'
                                          for step in result.steps[:self.playback.visible]):
                ratio = max(0, min(1, result.offset / selected.limit))
                marker = left + ratio * span
                if result.offset < 0:
                    marker -= 9
                elif result.offset >= selected.limit:
                    marker += 9
                color = PALETTE['error'] if failed else PALETTE['active']
                painter.setPen(QPen(QColor(color), 3))
                painter.drawLine(int(marker), int(bar_y - 4), int(marker), int(bar_y + 20))
                painter.setPen(QColor(color))
                painter.drawText(3, int(bar_y + 49),
                                 f'offset yêu cầu = {compact(result.offset)}' +
                                 (' · ngoài đoạn' if not 0 <= result.offset < selected.limit else ''))
        painter.end()


class Dashboard(QWidget):
    def __init__(self, parent_window):
        super().__init__()
        self.window = parent_window
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(13)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        left, layout = card('▣  Bảng phân đoạn')
        top = QHBoxLayout()
        top.addStretch()
        top.addWidget(button('＋ Thêm phân đoạn', self.window.add_segment, 'primary'))
        layout.addLayout(top)
        self.segment_table = data_table(['Segment', 'Base', 'Limit', 'Quyền'])
        self.segment_table.setMinimumHeight(160)
        layout.addWidget(self.segment_table, 1)
        actions = QHBoxLayout()
        actions.addWidget(button('✎  Sửa đã chọn', self.window.edit_segment))
        actions.addWidget(button('Xóa đã chọn', self.window.delete_segment, 'danger'))
        actions.addStretch()
        layout.addLayout(actions)
        grid.addWidget(left, 0, 0)

        right, layout = card('⇄  Dịch địa chỉ logic')
        fields = QGridLayout()
        for col, name in enumerate(['Segment', 'Offset', 'Thao tác']):
            fields.addWidget(QLabel(name), 0, col)
        self.segment_input = QLineEdit()
        self.segment_input.setPlaceholderText('Segment ID')
        self.offset_input = QLineEdit()
        self.offset_input.setPlaceholderText('Offset')
        self.operation = QComboBox()
        for label, access in [('Đọc (r)', 'r'), ('Ghi (w)', 'w'), ('Thực thi (x)', 'x')]:
            self.operation.addItem(label, access)
        fields.addWidget(self.segment_input, 1, 0)
        fields.addWidget(self.offset_input, 1, 1)
        fields.addWidget(self.operation, 1, 2)
        layout.addLayout(fields)
        commands = QHBoxLayout()
        commands.addWidget(button('▶ Dịch địa chỉ', self.window.translate, 'primary'), 1)
        commands.addWidget(button('☷ Từng bước', self.window.step_translate), 1)
        layout.addLayout(commands)
        self.result = QLabel('Chưa có kết quả. Hãy thêm phân đoạn và nhập địa chỉ logic.')
        self.result.setObjectName('infoBox')
        self.result.setWordWrap(True)
        self.result.setMinimumHeight(44)
        layout.addWidget(self.result)
        self.steps = QLabel('Các bước kiểm tra sẽ hiển thị tại đây.')
        self.steps.setObjectName('muted')
        self.steps.setWordWrap(True)
        layout.addWidget(self.steps)
        self.pipeline = PipelineWidget()
        layout.addWidget(self.pipeline)
        playback_commands = QHBoxLayout()
        playback_commands.addWidget(button('← Bước trước', self.window.previous_step))
        playback_commands.addWidget(button('Bước tiếp →', self.window.next_step))
        playback_commands.addWidget(button('↺ Chạy lại', self.window.restart_steps))
        layout.addLayout(playback_commands)
        grid.addWidget(right, 0, 1)

        memory, layout = card('▦  Sơ đồ vùng nhớ (Memory Map)')
        self.memory_map = MemoryMapWidget()
        layout.addWidget(self.memory_map, 1)
        grid.addWidget(memory, 1, 0)

        history, layout = card('◷  Lịch sử dịch địa chỉ')
        hrow = QHBoxLayout()
        hrow.addStretch()
        hrow.addWidget(button('Xem tất cả', lambda: self.window.show_page(1)))
        layout.addLayout(hrow)
        self.history_table = data_table(['Thời gian', 'Segment', 'Offset', 'Thao tác', 'Kết quả'])
        self.history_table.setMinimumHeight(170)
        layout.addWidget(self.history_table, 1)
        grid.addWidget(history, 1, 1)

        footer = QLabel('ⓘ Điều kiện: 0 ≤ Offset < Limit; thao tác phải nằm trong quyền truy cập của segment.')
        footer.setObjectName('infoBox')
        grid.addWidget(footer, 2, 0, 1, 2)

    def set_segments(self, segments):
        self.segment_table.setRowCount(len(segments))
        for row, segment in enumerate(segments):
            values = [segment.segment_id, segment.base, segment.limit,
                      display_permissions(segment.permissions)]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.segment_table.setItem(row, col, item)

    def set_result(self, text, success=None, details=''):
        self.result.setText(text)
        bg, fg = ('#e4f7ea', '#16683c') if success is True else (
            ('#fde9eb', '#aa2939') if success is False else ('#edf4ff', '#5373a3')
        )
        self.result.setStyleSheet(f'background:{bg};color:{fg};padding:13px;border-radius:8px;')
        self.steps.setText(details or 'Các bước kiểm tra sẽ hiển thị tại đây.')

    def address(self):
        return LogicalAddress(
            segment_id=int(self.segment_input.text().strip()),
            offset=int(self.offset_input.text().strip()),
            access=self.operation.currentData()
        )


class HistoryPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        frame, inner = card('◷  Toàn bộ lịch sử dịch địa chỉ')
        self.table = data_table(['Thời gian', 'Segment', 'Offset', 'Thao tác', 'Trạng thái', 'Địa chỉ vật lý'])
        inner.addWidget(self.table)
        layout.addWidget(frame)

    def set_history(self, records):
        self.table.setRowCount(len(records))
        for row, (timestamp, result) in enumerate(records):
            values = [timestamp, result.segment_id, result.offset, result.access,
                      result.status, result.physical_address if result.physical_address is not None else '—']
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))


class CSVPage(QWidget):
    def __init__(self, parent_window):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        frame, inner = card('▤  Nhập / Xuất CSV')
        description = QLabel(
            'Nhập bảng segment: segment_id,base,limit,permissions (permissions tùy chọn).\n'
            'Nhập địa chỉ logic: segment_id,offset,access (access tùy chọn).\n'
            'Các địa chỉ nhập vào sẽ được dịch bằng bảng segment hiện tại.'
        )
        description.setWordWrap(True)
        inner.addWidget(description)
        controls = QHBoxLayout()
        controls.addWidget(button('Nhập bảng Segment', parent_window.import_segments, 'primary'))
        controls.addWidget(button('Nhập địa chỉ CSV', parent_window.import_addresses))
        controls.addWidget(button('Xuất kết quả CSV', parent_window.export_results))
        inner.addLayout(controls)
        self.status = QLabel('Chưa nhập hoặc xuất tệp CSV.')
        self.status.setObjectName('infoBox')
        self.status.setWordWrap(True)
        inner.addWidget(self.status)
        samples = QLabel(
            'Ví dụ bảng segment:\nsegment_id,base,limit,permissions\n0,1000,200,rw\n1,3000,500,rx\n\n'
            'Ví dụ địa chỉ:\nsegment_id,offset,access\n0,25,r\n1,50,x'
        )
        samples.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        inner.addWidget(samples)
        inner.addStretch()
        layout.addWidget(frame)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.segments = []
        self.segment_table = None
        self.results = []
        self.history = []
        self.playback = Playback()
        self.logged_current = False
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
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(15, 25, 15, 18)
        sidebar_layout.setSpacing(10)
        brand = QLabel('▣  Segmentation\n     Simulator')
        brand.setObjectName('brand')
        sidebar_layout.addWidget(brand)
        sidebar_layout.addSpacing(27)
        self.nav = []
        for index, label in enumerate(['⌂  Trang chủ', '◷  Lịch sử', '▤  Nhập / Xuất CSV', 'ⓘ  Hướng dẫn']):
            nav_button = QPushButton(label)
            nav_button.setObjectName('nav')
            nav_button.clicked.connect(lambda checked=False, i=index: self.show_page(i))
            sidebar_layout.addWidget(nav_button)
            self.nav.append(nav_button)
        sidebar_layout.addStretch()
        info = QLabel('Mô phỏng phân đoạn bộ nhớ\nvà chuyển đổi địa chỉ logic\nsang địa chỉ vật lý.')
        info.setObjectName('sideInfo')
        info.setWordWrap(True)
        sidebar_layout.addWidget(info)
        outer.addWidget(sidebar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll, 1)
        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 25, 22, 23)
        content_layout.setSpacing(15)
        heading_row = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel('Mô phỏng Segmentation và Địa chỉ Logic')
        title.setObjectName('title')
        titles.addWidget(title)
        subtitle = QLabel('Quản lý segment, kiểm tra giới hạn, quyền truy cập và dịch địa chỉ.')
        subtitle.setObjectName('muted')
        titles.addWidget(subtitle)
        heading_row.addLayout(titles, 1)
        heading_row.addWidget(button('↻ Đặt lại', self.reset, 'secondary'))
        content_layout.addLayout(heading_row)
        self.pages = QStackedWidget()
        self.dashboard = Dashboard(self)
        self.history_page = HistoryPage()
        self.csv_page = CSVPage(self)
        self.pages.addWidget(self.dashboard)
        self.pages.addWidget(self.history_page)
        self.pages.addWidget(self.csv_page)
        self.pages.addWidget(self.build_help_page())
        content_layout.addWidget(self.pages, 1)
        self.show_page(0)
        self.refresh_segments()
        self.refresh_playback()

    def build_help_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        frame, inner = card('ⓘ  Hướng dẫn sử dụng')
        text = QLabel(
            '1. Nhấn Thêm phân đoạn để nhập Segment ID, Base, Limit và quyền truy cập.\n'
            '2. Nhập Segment, Offset và thao tác Đọc/Ghi/Thực thi.\n'
            '3. Nhấn Dịch địa chỉ để xem kết quả ngay lập tức.\n'
            '4. Nhấn Từng bước, sau đó dùng Bước tiếp / Bước trước để theo dõi mô phỏng.\n'
            '5. Theo dõi sơ đồ vùng nhớ và xem các kết quả đã dịch trong Lịch sử.\n'
            '6. Trang Nhập / Xuất CSV hỗ trợ đọc bảng segment, chạy nhiều địa chỉ và xuất kết quả.\n\n'
            'Quy tắc: 0 ≤ offset < limit, quyền truy cập phải được cấp, địa chỉ vật lý = base + offset.\n'
            'Bảng segment không cho phép ID trùng hoặc các khoảng vật lý chồng lấn.'
        )
        text.setWordWrap(True)
        inner.addWidget(text)
        inner.addStretch()
        layout.addWidget(frame)
        return page

    def show_page(self, index):
        self.pages.setCurrentIndex(index)
        for i, widget in enumerate(self.nav):
            widget.setProperty('active', 'true' if i == index else 'false')
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def selected_segment(self):
        index = self.dashboard.segment_table.currentRow()
        if not 0 <= index < len(self.segments):
            QMessageBox.information(self, 'Chọn phân đoạn', 'Hãy chọn một phân đoạn trong bảng trước.')
            return None
        return self.segments[index]

    def validate_segments(self, entries):
        return SegmentTable(entries) if entries else None

    def replace_segments(self, entries):
        table = self.validate_segments(entries)
        self.segments = list(entries)
        self.segment_table = table
        self.playback.clear()
        self.logged_current = False
        self.refresh_segments()
        self.refresh_playback()

    def refresh_segments(self):
        self.dashboard.set_segments(self.segments)
        self.dashboard.memory_map.set_state(self.segment_table, self.playback)

    def add_segment(self):
        dialog = SegmentDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            segment = dialog.get_segment()
            self.replace_segments([*self.segments, segment])
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, 'Không thể thêm phân đoạn', str(exc))

    def edit_segment(self):
        selected = self.selected_segment()
        if selected is None:
            return
        dialog = SegmentDialog(self, selected)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            updated = dialog.get_segment()
            entries = [updated if segment.segment_id == selected.segment_id else segment
                       for segment in self.segments]
            self.replace_segments(entries)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, 'Không thể sửa phân đoạn', str(exc))

    def delete_segment(self):
        selected = self.selected_segment()
        if selected is None:
            return
        answer = QMessageBox.question(self, 'Xác nhận xóa',
                                      f'Xóa Segment {selected.segment_id}?',
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.replace_segments([segment for segment in self.segments
                                   if segment.segment_id != selected.segment_id])

    def compute(self, complete):
        if self.segment_table is None:
            QMessageBox.warning(self, 'Chưa có bảng segment', 'Hãy thêm hoặc nhập ít nhất một segment.')
            return
        try:
            address = self.dashboard.address()
            result = self.segment_table.translate(address)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, 'Địa chỉ không hợp lệ', str(exc))
            return
        self.playback.load(result, complete=complete)
        self.logged_current = False
        self.refresh_playback()

    def translate(self):
        self.compute(True)

    def step_translate(self):
        self.compute(False)

    def next_step(self):
        self.playback.forward()
        self.refresh_playback()

    def previous_step(self):
        self.playback.backward()
        self.refresh_playback()

    def restart_steps(self):
        self.playback.restart()
        self.refresh_playback()

    def refresh_playback(self):
        playback = self.playback
        self.dashboard.pipeline.set_playback(playback)
        self.dashboard.memory_map.set_state(self.segment_table, playback)
        if playback.result is None:
            self.dashboard.set_result('Chưa có kết quả. Hãy nhập địa chỉ logic để bắt đầu.')
            return
        current = playback.result
        revealed = current.steps[:playback.visible]
        details = '\n'.join(f'{i + 1}. {step.title}: {step.description}'
                            for i, step in enumerate(revealed))
        if playback.complete:
            if current.status == 'OK':
                message = (f'✓ Dịch thành công: Segment {current.segment_id}, offset {current.offset} '
                           f'→ địa chỉ vật lý {current.physical_address} '
                           f'(base {current.base} + {current.offset}).')
            else:
                message = f'✕ {current.status}: {current.message}'
            self.dashboard.set_result(message, current.status == 'OK', details)
            if not self.logged_current:
                self.record_result(current)
                self.logged_current = True
        else:
            self.dashboard.set_result(f'Đang mô phỏng: bước {playback.visible}/{playback.total}. '
                                      'Kết quả cuối sẽ xuất hiện sau bước cuối.', None, details)

    def record_result(self, result):
        timestamp = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        self.history.append((timestamp, result))
        self.results.append(result)
        self.refresh_history()

    def refresh_history(self):
        self.history_page.set_history(self.history)
        records = self.history[-30:]
        table = self.dashboard.history_table
        table.setRowCount(len(records))
        for row, (timestamp, result) in enumerate(reversed(records)):
            values = [timestamp, result.segment_id, result.offset, result.access,
                      result.physical_address if result.status == 'OK' else result.status]
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(str(value)))

    def import_segments(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Nhập bảng segment CSV', '', 'CSV (*.csv)')
        if not path:
            return
        try:
            entries = load_segments(path)
            self.replace_segments(entries)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, 'Lỗi nhập bảng segment', str(exc))
            return
        self.csv_page.status.setText(f'✓ Đã nạp {len(entries)} segment từ {Path(path).name}.')

    def import_addresses(self):
        if self.segment_table is None:
            QMessageBox.warning(self, 'Chưa có bảng segment', 'Hãy thêm hoặc nhập segment trước.')
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Nhập danh sách địa chỉ CSV', '', 'CSV (*.csv)')
        if not path:
            return
        try:
            addresses = load_addresses(path)
            results = self.segment_table.translate_many(addresses)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, 'Lỗi nhập địa chỉ', str(exc))
            return
        for result in results:
            self.record_result(result)
        if results:
            self.playback.load(results[-1], complete=True)
            self.logged_current = True
            self.refresh_playback()
        successes = sum(result.status == 'OK' for result in results)
        self.csv_page.status.setText(
            f'✓ Đã dịch {len(results)} địa chỉ từ {Path(path).name}: '
            f'{successes} thành công, {len(results) - successes} lỗi. '
            'Kết quả đã thêm vào lịch sử và sẵn sàng để xuất CSV.'
        )

    def export_results(self):
        if not self.results:
            QMessageBox.information(self, 'Chưa có kết quả', 'Hãy dịch ít nhất một địa chỉ trước khi xuất CSV.')
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Xuất kết quả CSV', 'ket_qua_dich_dia_chi.csv', 'CSV (*.csv)')
        if not path:
            return
        try:
            save_results(path, self.results)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, 'Lỗi xuất CSV', str(exc))
            return
        self.csv_page.status.setText(f'✓ Đã xuất {len(self.results)} kết quả tới {Path(path).name}.')

    def reset(self):
        answer = QMessageBox.question(
            self, 'Đặt lại toàn bộ',
            'Xóa tất cả segment, kết quả và lịch sử dịch địa chỉ?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.segments = []
        self.segment_table = None
        self.results.clear()
        self.history.clear()
        self.logged_current = False
        self.playback.clear()
        self.dashboard.segment_input.clear()
        self.dashboard.offset_input.clear()
        self.dashboard.operation.setCurrentIndex(0)
        self.refresh_segments()
        self.refresh_playback()
        self.refresh_history()
        self.csv_page.status.setText('Đã đặt lại dữ liệu mô phỏng.')
        self.show_page(0)


def main():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = MainWindow()
    window.show()
    return app.exec()
