"""Real PySide6 button and navigation tests for src.gui.MainWindow."""
import csv
import os
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@unittest.skipUnless(find_spec("PySide6") is not None, "Install requirements-qt.txt")
class QtButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication, QPushButton
        from src import gui
        from src.segmentation import Segment

        cls.qt_app = QApplication.instance() or QApplication(["qt-button-tests", "-platform", "offscreen"])
        cls.gui = gui
        cls.Segment = Segment
        cls.QPushButton = QPushButton

    def setUp(self):
        self.window = self.gui.MainWindow()
        self.window.replace_segments([
            self.Segment(0, 1000, 400, "rx"),
            self.Segment(1, 2000, 250, "rw"),
        ])
        self.window.show()
        self.qt_app.processEvents()

    def tearDown(self):
        self.window.close()
        self.qt_app.processEvents()

    def click(self, part):
        buttons = self.window.findChildren(self.QPushButton)
        candidates = [button for button in buttons if part in button.text()]
        self.assertEqual(len(candidates), 1, f"Expected one button containing {part!r}")
        candidates[0].click()
        self.qt_app.processEvents()

    def enter_address(self, segment="0", offset="120", access="r"):
        dash = self.window.dashboard
        dash.segment_input.setText(str(segment))
        dash.offset_input.setText(str(offset))
        dash.operation.setCurrentIndex(dash.operation.findData(access))

    def test_translate_and_history_buttons(self):
        self.enter_address()
        self.click("Dịch địa chỉ")
        self.assertIn("1120", self.window.dashboard.result.text())
        self.assertEqual(self.window.dashboard.history_table.rowCount(), 1)
        self.click("Xem tất cả")
        self.assertEqual(self.window.pages.currentIndex(), 1)
        self.assertEqual(self.window.history_page.table.item(0, 5).text(), "1120")

    def test_step_buttons_do_not_show_result_early(self):
        self.enter_address(offset="-1")
        self.click("Từng bước")
        self.assertNotIn("SEGMENTATION_FAULT", self.window.dashboard.result.text())
        self.click("Bước tiếp")
        self.assertEqual(self.window.dashboard.history_table.rowCount(), 0)
        self.click("Bước tiếp")
        self.assertIn("SEGMENTATION_FAULT", self.window.dashboard.result.text())
        self.assertEqual(self.window.dashboard.history_table.rowCount(), 1)
        self.click("Bước trước")
        self.assertNotIn("SEGMENTATION_FAULT", self.window.dashboard.result.text())
        self.click("Chạy lại")
        self.assertEqual(self.window.playback.visible, 0)

    def test_add_and_remove_buttons(self):
        accepted = self.gui.QDialog.DialogCode.Accepted
        with patch.object(self.gui.SegmentDialog, "exec", return_value=accepted), \
             patch.object(self.gui.SegmentDialog, "get_segment", return_value=self.Segment(7, 5000, 8, "r")):
            self.click("Thêm phân đoạn")
        self.assertEqual(self.window.dashboard.segment_table.rowCount(), 3)
        self.window.dashboard.segment_table.setCurrentCell(2, 0)
        with patch.object(self.gui.QMessageBox, "question", return_value=self.gui.QMessageBox.StandardButton.Yes):
            self.click("Xóa đã chọn")
        self.assertEqual(self.window.dashboard.segment_table.rowCount(), 2)

    def test_csv_page_buttons_import_and_export(self):
        self.click("Nhập / Xuất CSV")
        self.assertEqual(self.window.pages.currentIndex(), 2)
        with tempfile.TemporaryDirectory() as temp:
            addresses = Path(temp) / "addresses.csv"
            addresses.write_text("segment_id,offset,access\n0,120,r\n0,400,r\n", encoding="utf-8")
            with patch.object(self.gui.QFileDialog, "getOpenFileName", return_value=(str(addresses), "")):
                self.click("Nhập địa chỉ CSV")
            self.assertIn("Đã dịch 2 địa chỉ", self.window.csv_page.status.text())
            target = Path(temp) / "results.csv"
            with patch.object(self.gui.QFileDialog, "getSaveFileName", return_value=(str(target), "")):
                self.click("Xuất kết quả CSV")
            with target.open(encoding="utf-8-sig", newline="") as source:
                records = list(csv.DictReader(source))
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["physical_address"], "1120")

    def test_reset_button_clears_table_and_history(self):
        self.enter_address()
        self.click("Dịch địa chỉ")
        with patch.object(self.gui.QMessageBox, "question", return_value=self.gui.QMessageBox.StandardButton.Yes):
            self.click("Đặt lại")
        self.assertEqual(self.window.dashboard.segment_table.rowCount(), 0)
        self.assertEqual(self.window.dashboard.history_table.rowCount(), 0)
        self.assertIsNone(self.window.playback.result)


if __name__ == "__main__":
    unittest.main()
