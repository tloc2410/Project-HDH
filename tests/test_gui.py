"""Integration tests for the PySide6 GUI in src.gui (not legacy Tkinter)."""
import csv
import os
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@unittest.skipUnless(find_spec("PySide6") is not None, "Install requirements-qt.txt")
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        from src import gui
        from src.segmentation import Segment

        cls.qt_app = QApplication.instance() or QApplication(["gui-tests", "-platform", "offscreen"])
        cls.gui = gui
        cls.Segment = Segment

    def setUp(self):
        self.window = self.gui.MainWindow()
        self.window.show()
        self.qt_app.processEvents()

    def tearDown(self):
        self.window.close()
        self.qt_app.processEvents()

    def load_segments(self):
        self.window.replace_segments([
            self.Segment(0, 1000, 400, "rx"),
            self.Segment(1, 2000, 250, "rw"),
            self.Segment(2, 3000, 200, "rwx"),
        ])

    def enter_address(self, segment="0", offset="120", access="r"):
        self.window.dashboard.segment_input.setText(str(segment))
        self.window.dashboard.offset_input.setText(str(offset))
        selector = self.window.dashboard.operation
        selector.setCurrentIndex(selector.findData(access))

    def test_initial_window_starts_with_empty_table_and_four_pages(self):
        self.assertEqual(self.window.pages.count(), 4)
        self.assertEqual(self.window.dashboard.segment_table.rowCount(), 0)
        self.assertIsNone(self.window.segment_table)
        self.assertIsNone(self.window.playback.result)
        self.assertEqual(len(self.window.history), 0)

    def test_translate_success_shows_physical_address_and_history(self):
        self.load_segments()
        self.enter_address()
        self.window.translate()
        self.assertEqual(self.window.playback.result.status, "OK")
        self.assertEqual(self.window.playback.physical_address, 1120)
        self.assertIn("1120", self.window.dashboard.result.text())
        self.assertEqual(self.window.dashboard.history_table.rowCount(), 1)
        self.assertEqual(self.window.history_page.table.rowCount(), 1)
        self.assertIs(self.window.dashboard.memory_map.table, self.window.segment_table)

    def test_translation_reports_bounds_permission_and_missing_segment(self):
        self.load_segments()
        cases = [
            ("0", "400", "r", "SEGMENTATION_FAULT"),
            ("0", "-1", "r", "SEGMENTATION_FAULT"),
            ("0", "100", "w", "PROTECTION_FAULT"),
            ("99", "0", "r", "SEGMENT_NOT_FOUND"),
        ]
        for segment, offset, access, expected in cases:
            with self.subTest(expected=expected, segment=segment, offset=offset):
                self.enter_address(segment, offset, access)
                self.window.translate()
                self.assertEqual(self.window.playback.result.status, expected)
                self.assertIsNone(self.window.playback.physical_address)
                self.assertIn(expected, self.window.dashboard.result.text())
        self.assertEqual(len(self.window.history), len(cases))

    def test_step_forward_backward_restart_hides_unrevealed_result(self):
        self.load_segments()
        self.enter_address()
        self.window.step_translate()
        self.assertEqual(self.window.playback.visible, 0)
        self.assertNotIn("1120", self.window.dashboard.result.text())
        self.assertEqual(len(self.window.history), 0)
        for _ in range(self.window.playback.total - 1):
            self.window.next_step()
            self.assertIsNone(self.window.playback.physical_address)
            self.assertEqual(len(self.window.history), 0)
        self.window.next_step()
        self.assertEqual(self.window.playback.physical_address, 1120)
        self.assertEqual(len(self.window.history), 1)
        self.window.next_step()
        self.assertEqual(len(self.window.history), 1)
        self.window.previous_step()
        self.assertIsNone(self.window.playback.physical_address)
        self.assertNotIn("1120", self.window.dashboard.result.text())
        self.window.restart_steps()
        self.assertEqual(self.window.playback.visible, 0)
        self.assertIsNone(self.window.playback.physical_address)

    def test_failed_step_appears_only_at_failure_stage(self):
        self.load_segments()
        self.enter_address(offset="400")
        self.window.step_translate()
        self.assertNotIn("SEGMENTATION_FAULT", self.window.dashboard.result.text())
        self.window.next_step()
        self.assertNotIn("SEGMENTATION_FAULT", self.window.dashboard.result.text())
        self.window.next_step()
        self.assertIn("SEGMENTATION_FAULT", self.window.dashboard.result.text())
        self.assertEqual(len(self.window.history), 1)
        self.assertIn("Lỗi", self.window.dashboard.pipeline.labels[1].text())
        self.assertIn("Bỏ qua", self.window.dashboard.pipeline.labels[2].text())
        self.window.previous_step()
        self.assertNotIn("SEGMENTATION_FAULT", self.window.dashboard.result.text())

    def test_bad_input_does_not_erase_previous_result(self):
        self.load_segments()
        self.enter_address()
        self.window.translate()
        previous = self.window.playback.result
        self.window.dashboard.offset_input.setText("not-a-number")
        with patch.object(self.gui.QMessageBox, "warning") as warning:
            self.window.translate()
        warning.assert_called_once()
        self.assertIs(self.window.playback.result, previous)
        self.assertEqual(self.window.playback.physical_address, 1120)
        self.assertEqual(len(self.window.history), 1)

    def test_add_edit_delete_segments_and_reject_overlap(self):
        self.load_segments()
        accepted = self.gui.QDialog.DialogCode.Accepted
        with patch.object(self.gui.SegmentDialog, "exec", return_value=accepted), \
             patch.object(self.gui.SegmentDialog, "get_segment", return_value=self.Segment(7, 5000, 80, "rw")):
            self.window.add_segment()
        self.assertEqual(len(self.window.segments), 4)
        self.window.dashboard.segment_table.setCurrentCell(3, 0)
        before = self.window.segment_table
        with patch.object(self.gui.SegmentDialog, "exec", return_value=accepted), \
             patch.object(self.gui.SegmentDialog, "get_segment", return_value=self.Segment(7, 1100, 80, "rw")), \
             patch.object(self.gui.QMessageBox, "warning") as warning:
            self.window.edit_segment()
        warning.assert_called_once()
        self.assertIs(self.window.segment_table, before)
        self.assertEqual(self.window.segments[-1].base, 5000)
        with patch.object(self.gui.SegmentDialog, "exec", return_value=accepted), \
             patch.object(self.gui.SegmentDialog, "get_segment", return_value=self.Segment(7, 6000, 80, "rw")):
            self.window.edit_segment()
        self.assertEqual(self.window.segments[-1].base, 6000)
        with patch.object(self.gui.QMessageBox, "question", return_value=self.gui.QMessageBox.StandardButton.Yes):
            self.window.delete_segment()
        self.assertEqual(len(self.window.segments), 3)
        self.assertNotIn(7, [s.segment_id for s in self.window.segments])

    def test_segment_csv_import_is_atomic(self):
        with tempfile.TemporaryDirectory() as temp:
            valid = Path(temp) / "segments.csv"
            valid.write_text("segment_id,base,limit,permissions\n8,5000,50,rw\n", encoding="utf-8")
            with patch.object(self.gui.QFileDialog, "getOpenFileName", return_value=(str(valid), "")):
                self.window.import_segments()
            self.assertEqual(self.window.segments[0].segment_id, 8)
            previous = self.window.segment_table
            invalid = Path(temp) / "bad.csv"
            invalid.write_text("segment_id,base\n8,5000\n", encoding="utf-8")
            with patch.object(self.gui.QFileDialog, "getOpenFileName", return_value=(str(invalid), "")), \
                 patch.object(self.gui.QMessageBox, "warning") as warning:
                self.window.import_segments()
            warning.assert_called_once()
            self.assertIs(self.window.segment_table, previous)
            self.assertEqual(self.window.dashboard.segment_table.rowCount(), 1)

    def test_address_csv_import_and_result_export(self):
        self.load_segments()
        with tempfile.TemporaryDirectory() as temp:
            addresses = Path(temp) / "addresses.csv"
            addresses.write_text(
                "segment_id,offset,access\n0,120,r\n0,400,r\n0,100,w\n99,0,r\n",
                encoding="utf-8",
            )
            with patch.object(self.gui.QFileDialog, "getOpenFileName", return_value=(str(addresses), "")):
                self.window.import_addresses()
            self.assertEqual(len(self.window.results), 4)
            self.assertEqual(len(self.window.history), 4)
            self.assertEqual(self.window.results[0].physical_address, 1120)
            self.assertEqual(
                {item.status for item in self.window.results},
                {"OK", "SEGMENTATION_FAULT", "PROTECTION_FAULT", "SEGMENT_NOT_FOUND"},
            )
            target = Path(temp) / "results.csv"
            with patch.object(self.gui.QFileDialog, "getSaveFileName", return_value=(str(target), "")):
                self.window.export_results()
            with target.open(encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[0]["physical_address"], "1120")
            self.assertEqual(rows[1]["status"], "SEGMENTATION_FAULT")

    def test_reset_clears_state_and_returns_to_dashboard(self):
        self.load_segments()
        self.enter_address()
        self.window.translate()
        self.window.show_page(2)
        with patch.object(self.gui.QMessageBox, "question", return_value=self.gui.QMessageBox.StandardButton.Yes):
            self.window.reset()
        self.assertEqual(len(self.window.segments), 0)
        self.assertIsNone(self.window.segment_table)
        self.assertEqual(self.window.dashboard.segment_table.rowCount(), 0)
        self.assertEqual(len(self.window.history), 0)
        self.assertEqual(len(self.window.results), 0)
        self.assertEqual(self.window.dashboard.segment_input.text(), "")
        self.assertEqual(self.window.pages.currentIndex(), 0)


if __name__ == "__main__":
    unittest.main()
