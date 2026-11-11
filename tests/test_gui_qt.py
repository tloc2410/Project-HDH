"""Kiểm tra kết nối giữa các nút PySide6 và bộ mô phỏng."""

import csv
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


@unittest.skipUnless(find_spec("PySide6"), "Cài requirements-qt.txt để kiểm thử PySide6")
class QtIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication, QPushButton
        from src.gui_qt.controller import SimulatorController
        from src.gui_qt.main_window import MainWindow

        cls.app = QApplication.instance() or QApplication(["tests", "-platform", "offscreen"])
        cls.window_type = MainWindow
        cls.controller_type = SimulatorController
        cls.button_type = QPushButton

    def setUp(self):
        self.window = self.window_type()
        self.controller = self.controller_type(self.window)
        self.dashboard = self.window.dashboard
        self.window.show()
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window.close)
        warning = patch("src.gui_qt.controller.QMessageBox.warning")
        self.warning = warning.start()
        self.addCleanup(warning.stop)

    def click(self, text):
        button = next(button for button in self.window.findChildren(self.button_type) if text in button.text())
        self.assertTrue(button.isEnabled())
        button.click()
        self.app.processEvents()

    def enter_address(self, segment, offset, operation="r"):
        self.dashboard.segment_input.setText(segment)
        self.dashboard.offset_input.setText(offset)
        self.dashboard.operation.setCurrentIndex(self.dashboard.operation.findData(operation))

    def test_translate_history_and_reset_buttons(self):
        self.enter_address("0", "120")
        self.click("Dịch địa chỉ")
        self.assertIn("1120", self.dashboard.result.text())
        self.assertEqual(self.dashboard.history_table.rowCount(), 1)
        self.click("Xem tất cả")
        self.assertEqual(self.window.pages.currentIndex(), 1)
        self.assertIn("1120", self.window.history_table.item(0, 4).text())
        self.click("Đặt lại")
        self.assertEqual(self.window.pages.currentIndex(), 0)
        self.assertEqual(self.window.history_table.rowCount(), 0)
        self.assertEqual(self.dashboard.segment_input.text(), "")

    def test_step_mode_reveals_fault_and_records_it_once(self):
        self.enter_address("0", "-1")
        self.click("Từng bước")
        self.assertNotIn("SEGMENTATION_FAULT", self.dashboard.result.text())
        self.click("Bước tiếp")
        self.assertEqual(self.dashboard.history_table.rowCount(), 0)
        self.click("Bước tiếp")
        self.assertIn("SEGMENTATION_FAULT", self.dashboard.result.text())
        self.controller.next_step()
        self.assertEqual(self.dashboard.history_table.rowCount(), 1)

    def test_edit_buttons_keep_valid_table_after_rejected_overlap(self):
        from PySide6.QtWidgets import QDialog, QMessageBox

        segment = {"id": "7", "base": "5000", "limit": "8", "permission": "rw-"}
        with patch("src.gui_qt.dashboard.SegmentDialog.exec", return_value=QDialog.DialogCode.Accepted):
            with patch("src.gui_qt.dashboard.SegmentDialog.get_data", return_value=segment):
                self.click("Thêm phân đoạn")
            self.assertEqual(self.controller.table.segments[-1].segment_id, 7)
            self.dashboard.segment_table.selectRow(self.dashboard.segment_table.rowCount() - 1)
            with patch("src.gui_qt.dashboard.SegmentDialog.get_data", return_value={**segment, "base": "1000"}):
                self.click("Sửa đã chọn")
            self.warning.assert_called_once()
            self.assertEqual(self.controller.table.segments[-1].base, 5000)
            with patch("src.gui_qt.dashboard.SegmentDialog.get_data", return_value={**segment, "base": "6000"}):
                self.click("Sửa đã chọn")
        self.assertEqual(self.controller.table.segments[-1].base, 6000)
        with patch("src.gui_qt.dashboard.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            self.click("Xóa đã chọn")
        self.assertNotIn(7, {segment.segment_id for segment in self.controller.table.segments})

    def test_csv_buttons_load_translate_and_export(self):
        from src.gui_qt.controller import PROJECT_ROOT

        self.click("Nhập / Xuất CSV")
        self.assertFalse(self.window.csv_page.export_button.isEnabled())
        paths = [(str(PROJECT_ROOT / "input" / filename), "") for filename in ("segments.csv", "addresses.csv")]
        with patch("src.gui_qt.controller.QFileDialog.getOpenFileName", side_effect=paths):
            self.click("Nạp bảng phân đoạn")
            self.click("Dịch danh sách địa chỉ")
        self.assertIn("Đã dịch 10 địa chỉ", self.window.csv_page.status.text())
        with TemporaryDirectory() as temp:
            target = Path(temp) / "result.csv"
            with patch("src.gui_qt.controller.QFileDialog.getSaveFileName", return_value=(str(target), "")):
                self.click("Xuất kết quả")
            with target.open(encoding="utf-8-sig", newline="") as exported:
                results = list(csv.DictReader(exported))
        self.assertEqual(len(results), 10)
        self.assertEqual(results[0]["physical_address"], "1120")
        self.assertIn("SEGMENTATION_FAULT", {result["status"] for result in results})
