from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QFrame, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QComboBox, QMessageBox, QDialog, QAbstractItemView)
from .segment_dialog import SegmentDialog


def btn(label, callback=None, role=None):
    b = QPushButton(label)
    if role:
        b.setObjectName(role)
    if callback:
        b.clicked.connect(callback)
    return b


def card(title):
    f = QFrame()
    f.setObjectName('card')
    l = QVBoxLayout(f)
    l.setContentsMargins(16, 15, 16, 15)
    l.setSpacing(11)
    h = QLabel(title)
    h.setObjectName('section')
    l.addWidget(h)
    return f, l


def table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t.verticalHeader().hide()
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setAlternatingRowColors(True)
    return t


def make_history_table():
    view = table(['Thời gian', 'Segment', 'Offset', 'Thao tác', 'Kết quả'])
    header = view.horizontalHeader()
    for column, width in enumerate((130, 74, 53, 66)):
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        view.setColumnWidth(column, width)
    return view


def fill_history(history_table, records):
    history_table.setRowCount(len(records))
    keys = ('time', 'segment', 'offset', 'operation', 'result')
    for row, record in enumerate(records):
        for column, key in enumerate(keys):
            value = record.get(key, '') if isinstance(record, dict) else (
                record[column] if column < len(record) else '')
            text = str(value)
            item = QTableWidgetItem(text)
            item.setToolTip(text)
            history_table.setItem(row, column, item)


class Dashboard(QWidget):
    """Hiển thị bảng phân đoạn, kết quả dịch và lịch sử gần nhất."""
    add_requested = Signal(dict)
    edit_requested = Signal(dict)
    delete_requested = Signal(object)
    translate_requested = Signal(dict)
    step_requested = Signal(dict)
    next_step_requested = Signal()
    history_requested = Signal()

    def __init__(self):
        super().__init__()
        self._segments = []
        self.build()

    def build(self):
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(13)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)

        left, ll = card('▣  Bảng phân đoạn')
        top = QHBoxLayout()
        top.addStretch()
        top.addWidget(btn('＋ Thêm phân đoạn', self._add, 'primary'))
        ll.addLayout(top)
        self.segment_table = table(['Segment', 'Base', 'Limit', 'Quyền'])
        self.segment_table.setMinimumHeight(160)
        ll.addWidget(self.segment_table, 1)
        actions = QHBoxLayout()
        actions.addWidget(btn('✎  Sửa đã chọn', self._edit, 'secondary'))
        actions.addWidget(btn('Xóa đã chọn', self._delete, 'danger'))
        actions.addStretch()
        ll.addLayout(actions)
        grid.addWidget(left, 0, 0)

        right, rl = card('⇄  Dịch địa chỉ logic')
        fields = QGridLayout()
        for col, label in enumerate(['Segment', 'Offset', 'Thao tác']):
            fields.addWidget(QLabel(label), 0, col)
        self.segment_input = QLineEdit()
        self.segment_input.setPlaceholderText('Segment ID')
        self.offset_input = QLineEdit()
        self.offset_input.setPlaceholderText('Offset')
        self.operation = QComboBox()
        self.operation.addItem('Đọc (r)', 'r')
        self.operation.addItem('Ghi (w)', 'w')
        self.operation.addItem('Thực thi (x)', 'x')
        fields.addWidget(self.segment_input, 1, 0)
        fields.addWidget(self.offset_input, 1, 1)
        fields.addWidget(self.operation, 1, 2)
        rl.addLayout(fields)
        row = QHBoxLayout()
        row.addWidget(btn('▶  Dịch địa chỉ', self._translate, 'primary'), 1)
        row.addWidget(btn('☷  Từng bước', self._step, 'secondary'), 1)
        rl.addLayout(row)
        self.result = QLabel('Chưa có kết quả. Hãy thêm phân đoạn và nhập địa chỉ logic.')
        self.result.setTextFormat(Qt.TextFormat.PlainText)
        self.result.setObjectName('infoBox')
        self.result.setWordWrap(True)
        rl.addWidget(self.result)
        self.steps = QLabel('Các bước kiểm tra sẽ hiển thị tại đây.')
        self.steps.setTextFormat(Qt.TextFormat.PlainText)
        self.steps.setObjectName('muted')
        self.steps.setWordWrap(True)
        rl.addWidget(self.steps)
        self.next_step_button = btn('Bước tiếp →', lambda: self.next_step_requested.emit(), 'secondary')
        self.set_next_step_enabled(False)
        rl.addWidget(self.next_step_button)
        rl.addStretch()
        grid.addWidget(right, 0, 1)

        memory, ml = card('▦  Sơ đồ vùng nhớ (Memory Map)')
        self.memory_slot = QFrame()
        memory_layout = QVBoxLayout(self.memory_slot)
        memory_layout.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(self.memory_slot, 1)
        grid.addWidget(memory, 1, 0)

        history, hl = card('◷  Lịch sử dịch địa chỉ')
        hrow = QHBoxLayout()
        hrow.addStretch()
        hrow.addWidget(btn('Xem tất cả', lambda: self.history_requested.emit(), 'secondary'))
        hl.addLayout(hrow)
        self.history_table = make_history_table()
        self.history_table.setMinimumHeight(170)
        hl.addWidget(self.history_table, 1)
        grid.addWidget(history, 1, 1)
        foot = QLabel('ⓘ  Điều kiện: 0 ≤ Offset < Limit; thao tác phải phù hợp quyền truy cập của phân đoạn.')
        foot.setObjectName('infoBox')
        grid.addWidget(foot, 2, 0, 1, 2)

    def set_segments(self, segments):
        selected_rows = self.segment_table.selectionModel().selectedRows()
        selected_id = self._segments[selected_rows[0].row()]['id'] if selected_rows else None
        self._segments = [dict(s) for s in segments]
        self.segment_table.clearSelection()
        self.segment_table.setRowCount(len(self._segments))
        for row, seg in enumerate(self._segments):
            for col, key in enumerate(('id', 'base', 'limit', 'permission')):
                item = QTableWidgetItem(str(seg.get(key, '')))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.segment_table.setItem(row, col, item)
            if seg.get('id') == selected_id and selected_id is not None:
                self.segment_table.selectRow(row)

    def show_result(self, message, success=None, details=''):
        self.result.setText(str(message))
        bg, fg = ('#e4f7ea', '#16683c') if success is True else (
            ('#fde9eb', '#aa2939') if success is False else ('#edf4ff', '#5373a3'))
        self.result.setStyleSheet(f'background:{bg};color:{fg};padding:13px;border-radius:8px;')
        self.steps.setText(str(details) if details else 'Các bước kiểm tra sẽ hiển thị tại đây.')

    def set_next_step_enabled(self, enabled):
        self.next_step_button.setEnabled(enabled)

    def set_history(self, records):
        fill_history(self.history_table, records)

    def set_memory_widget(self, widget):
        layout = self.memory_slot.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        layout.addWidget(widget)

    def _selected(self):
        selected_rows = self.segment_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, 'Chọn phân đoạn', 'Hãy chọn một phân đoạn trong bảng trước.')
            return None
        return self._segments[selected_rows[0].row()]

    def _add(self):
        dialog = SegmentDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.add_requested.emit(dialog.get_data())

    def _edit(self):
        selected = self._selected()
        if selected is None:
            return
        dialog = SegmentDialog(self, selected)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.edit_requested.emit(dialog.get_data())

    def _delete(self):
        selected = self._selected()
        if selected is None:
            return
        answer = QMessageBox.question(self, 'Xác nhận xóa',
            f'Xóa Segment {selected.get("id")}?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(selected.get('id'))

    def _address_data(self):
        return {'segment_id': self.segment_input.text().strip(),
                'offset': self.offset_input.text().strip(), 'operation': self.operation.currentData()}

    def _translate(self):
        self.translate_requested.emit(self._address_data())

    def _step(self):
        self.step_requested.emit(self._address_data())
