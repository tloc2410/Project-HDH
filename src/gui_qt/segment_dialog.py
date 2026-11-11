from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, QDialogButtonBox

class SegmentDialog(QDialog):
    """Nhập thông tin phân đoạn để gửi cho bộ điều khiển."""
    def __init__(self, parent=None, segment=None):
        super().__init__(parent)
        self.setWindowTitle('Sửa phân đoạn' if segment else 'Thêm phân đoạn')
        self.setMinimumWidth(370)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.segment_id = QLineEdit()
        self.base = QLineEdit()
        self.limit = QLineEdit()
        self.permission = QComboBox()
        self.permission.addItems(['r--', 'rw-', 'r-x', 'rwx', '-w-', '--x', '-wx'])
        if segment is not None:
            self.segment_id.setText(str(segment.get('id', '')))
            self.segment_id.setReadOnly(True)
            self.base.setText(str(segment.get('base', '')))
            self.limit.setText(str(segment.get('limit', '')))
            permissions = segment.get('permission', 'r')
            self.permission.setCurrentText(''.join(
                flag if flag in permissions else '-' for flag in 'rwx'
            ))
        form.addRow('Segment ID:', self.segment_id)
        form.addRow('Base:', self.base)
        form.addRow('Limit:', self.limit)
        form.addRow('Quyền:', self.permission)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Lưu')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Hủy')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        return {'id': self.segment_id.text().strip(), 'base': self.base.text().strip(),
                'limit': self.limit.text().strip(), 'permission': self.permission.currentText()}
