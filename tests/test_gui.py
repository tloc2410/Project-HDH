"""Integration tests with real Tk widgets and the real translation core.

Only file dialogs and modal error dialogs are mocked. Headless hosts skip
these tests; Windows CI checks its Tk display before running the suite.
"""
import csv
import gc
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from src.gui import DISPLAY_LIMIT, PROJECT_ROOT, SegmentationApp
from src.segmentation import Segment, SegmentTable


class GuiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            probe = tk.Tk()
            probe.withdraw()
            probe.destroy()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"Tk display/runtime unavailable: {exc}")

    def setUp(self):
        # Use a fresh window: a mapped layout test can leave realized geometry
        # cached on a withdrawn shared root, hiding later geometry requests.
        self.root = tk.Tk()
        self.root.withdraw()
        self.callback_errors = []
        self.root.report_callback_exception = lambda *args: self.callback_errors.append(args)
        self.error_patch = patch("src.gui.messagebox.showerror")
        self.error_dialog = self.error_patch.start()
        self.addCleanup(self.error_patch.stop)
        self.app = SegmentationApp(self.root)
        self.root.update_idletasks()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def tearDown(self):
        if self.app is not None:
            self.app.destroy()
            self.app = None
        # Finalize Tk variables on the UI thread before another CSV worker.
        gc.collect()
        self.root.update_idletasks()
        self.root.destroy()
        self.assertEqual(self.callback_errors, [], "Tk callback raised an exception")

    def wait_until(self, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.root.update_idletasks()
        self.assertTrue(predicate(), "GUI operation did not finish before timeout")

    def wait_for_worker(self):
        self.wait_until(lambda: not self.app._job_running)

    def csv_file(self, name, text):
        path = Path(self.temp_dir.name) / name
        path.write_text(text, encoding="utf-8")
        return path

    def canvas_text(self, canvas):
        return "\n".join(canvas.itemcget(item, "text") for item in canvas.find_all()
                         if canvas.type(item) == "text")

    def visible_result_text(self):
        return "\n".join((self.app.result_title.cget("text"),
                          self.app.result_detail.cget("text"),
                          self.app.trace_text.get("1.0", "end"),
                          self.app.status_var.get(),
                          self.canvas_text(self.app.map_canvas)))

    def assert_no_physical_result(self):
        self.assertIsNone(self.app.playback.physical_address)
        self.assertFalse(self.app.map_canvas.find_withtag("physical_marker"))

    def scheduled_callbacks(self):
        return set(self.root.tk.call("after", "info"))

    def load_scenario(self, name):
        self.app.scenario_var.set(name)
        self.app.scenario_button.invoke()

    def test_startup_and_translate_button_show_physical_address(self):
        self.assertEqual(len(self.app.segment_tree.get_children()), 3)
        self.assert_no_physical_result()
        self.app.translate_button.invoke()
        self.assertEqual(self.app.single_result.physical_address, 1120)
        self.assertEqual(self.app.playback.visible, 4)
        self.assertIn("1120", self.app.result_title.cget("text"))
        self.assertTrue(self.app.map_canvas.find_withtag("physical_marker"))
        self.assertTrue(self.app.next_button.instate(["disabled"]))
        self.error_dialog.assert_not_called()

    def test_startup_geometry_reserves_title_bar_and_taskbar(self):
        width, height = map(int, self.root.geometry().split("+")[0].split("x"))
        self.assertLessEqual(width, self.root.winfo_screenwidth() - 80)
        self.assertLessEqual(height, self.root.winfo_screenheight() - 120)
        self.assertEqual(self.app.status_label.pack_info()["side"], "bottom")

    def test_default_layout_keeps_map_rows_and_editor_controls_visible(self):
        # A withdrawn window keeps children at 1x1. Allocate real widgets
        # fully transparent and without a taskbar entry; show no visible app.
        self.root.attributes("-alpha", 0)
        self.root.overrideredirect(True)
        try:
            # Keep the layout baseline independent of the CI desktop size.
            self.root.geometry("1180x724")
            self.root.deiconify()
            self.root.update()
            self.assertEqual(self.app.notebook.select(), str(self.app.simulator_tab))
            self.assertGreaterEqual(self.app.map_canvas.winfo_height(), 190)
            for row in self.app.segment_tree.get_children():
                bounds = self.app.segment_tree.bbox(row)
                self.assertTrue(bounds, "A sample segment row is outside the viewport")
                self.assertLessEqual(bounds[1] + bounds[3], self.app.segment_tree.winfo_height())
            for offset, access in (("120", "Đọc (r)"), ("400", "Đọc (r)"), ("100", "Ghi (w)")):
                for button in (self.app.step_button, self.app.translate_button):
                    with self.subTest(offset=offset, access=access, mode=button.cget("text")):
                        self.app.offset_var.set(offset)
                        self.app.access_var.set(access)
                        button.invoke()
                        self.root.update()
                        self.assertGreaterEqual(self.app.map_canvas.winfo_height(), 190,
                                                "Physical map and offset labels are clipped")
            self.app.notebook.select(self.app.editor_tab)
            self.root.update()
            editor = self.app.editor_tab
            for button in (self.app.add_button, self.app.remove_button):
                self.assertGreater(button.winfo_width(), 1)
                self.assertGreater(button.winfo_height(), 1)
                x = button.winfo_rootx() - editor.winfo_rootx()
                y = button.winfo_rooty() - editor.winfo_rooty()
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(x + button.winfo_width(), editor.winfo_width())
                self.assertLessEqual(y + button.winfo_height(), editor.winfo_height())
        finally:
            self.root.withdraw()
            self.root.overrideredirect(False)
            self.root.attributes("-alpha", 1)

    def test_step_forward_back_and_restart_hide_future_result(self):
        self.app.step_button.invoke()
        self.assertEqual(self.app.playback.visible, 0)
        self.assertTrue(self.app.previous_button.instate(["disabled"]))
        for stage in range(4):
            self.assertEqual(self.app.playback.visible, stage)
            self.assert_no_physical_result()
            self.assertNotIn("1120", self.visible_result_text())
            self.app.next_button.invoke()
        self.assertEqual(self.app.playback.physical_address, 1120)
        self.app.previous_button.invoke()
        self.assertEqual(self.app.playback.visible, 3)
        self.assert_no_physical_result()
        self.assertNotIn("1120", self.visible_result_text())
        self.app.restart_button.invoke()
        self.assertEqual(self.app.playback.visible, 0)
        self.assert_no_physical_result()
        self.assertFalse(self.app.map_canvas.find_withtag("offset_marker"))
        self.assertNotIn("1120", self.visible_result_text())

    def test_step_failure_is_revealed_only_at_failed_stage(self):
        self.app.offset_var.set("400")
        self.app.step_button.invoke()
        self.assertNotIn("SEGMENTATION_FAULT", self.visible_result_text())
        self.app.next_button.invoke()
        self.assertNotIn("SEGMENTATION_FAULT", self.visible_result_text())
        self.app.next_button.invoke()
        self.assertIn("SEGMENTATION_FAULT", self.app.result_title.cget("text"))
        self.assert_no_physical_result()
        self.assertTrue(self.app.pipeline_canvas.find_withtag("error"))
        self.assertEqual(len(self.app.pipeline_canvas.find_withtag("skipped")), 2)
        self.assertTrue(self.app.next_button.instate(["disabled"]))
        self.app.previous_button.invoke()
        self.assertNotIn("SEGMENTATION_FAULT", self.visible_result_text())

    def test_restart_after_full_result_hides_final_error_status(self):
        self.app.offset_var.set("400")
        self.app.translate_button.invoke()
        self.assertIn("SEGMENTATION_FAULT", self.visible_result_text())
        self.app.restart_button.invoke()
        self.assertNotIn("SEGMENTATION_FAULT", self.visible_result_text())
        self.assert_no_physical_result()

    def test_all_sample_scenarios_use_real_buttons_and_expected_outcomes(self):
        expected = {
            "Hợp lệ · đọc": ("OK", 1120),
            "Hợp lệ · ghi": ("OK", 2050),
            "Hợp lệ · thực thi": ("OK", 1000),
            "Biên cuối · limit − 1": ("OK", 1399),
            "Lỗi · offset = limit": ("SEGMENTATION_FAULT", None),
            "Lỗi · offset âm": ("SEGMENTATION_FAULT", None),
            "Lỗi · quyền ghi": ("PROTECTION_FAULT", None),
            "Lỗi · quyền thực thi": ("PROTECTION_FAULT", None),
            "Lỗi · thiếu segment": ("SEGMENT_NOT_FOUND", None),
        }
        for name, (status, physical) in expected.items():
            with self.subTest(name=name):
                self.load_scenario(name)
                self.assertEqual(self.app.playback.visible, 0)
                self.assert_no_physical_result()
                self.app.translate_button.invoke()
                self.assertEqual(self.app.single_result.status, status)
                self.assertEqual(self.app.playback.physical_address, physical)
                if physical is None:
                    self.assertIn(status, self.app.result_title.cget("text"))
                    self.assert_no_physical_result()
                    translation = self.app.pipeline_canvas.find_withtag("translation")[0]
                    self.assertIn("skipped", self.app.pipeline_canvas.gettags(translation))
                else:
                    self.assertIn(str(physical), self.app.result_title.cget("text"))
        self.error_dialog.assert_not_called()

    def test_autoplay_finishes_and_pause_cancels_future_tick(self):
        self.app.step_button.invoke()
        self.app.speed_var.set("2 giây")
        self.app.play_button.invoke()
        pending = self.app._play_after
        self.assertIn(pending, self.scheduled_callbacks())
        self.app.play_button.invoke()
        self.assertIsNone(self.app._play_after)
        self.assertNotIn(pending, self.scheduled_callbacks())
        self.assertEqual(self.app.playback.visible, 0)
        self.app.speed_var.set("0,5 giây")
        self.app.play_button.invoke()
        self.wait_until(lambda: self.app.playback.complete, timeout=5)
        self.assertIsNone(self.app._play_after)
        self.assertEqual(self.app.playback.physical_address, 1120)
        self.assertIn("Tự chạy", self.app.play_button.cget("text"))

    def test_new_scenario_and_table_edit_cancel_active_playback(self):
        self.app.step_button.invoke()
        self.app.play_button.invoke()
        pending = self.app._play_after
        self.load_scenario("Lỗi · quyền ghi")
        self.assertIsNone(self.app._play_after)
        self.assertNotIn(pending, self.scheduled_callbacks())
        self.assertEqual(self.app.playback.visible, 0)
        self.assertEqual(self.app.offset_var.get(), "100")
        self.app.play_button.invoke()
        pending = self.app._play_after
        self.app.add_button.invoke()
        self.assertEqual(len(self.app.table.segments), 4)
        self.assertIsNone(self.app._play_after)
        self.assertNotIn(pending, self.scheduled_callbacks())
        self.assertIsNone(self.app.playback.result)
        self.assert_no_physical_result()

    def test_destroy_cancels_scheduled_playback(self):
        self.app.step_button.invoke()
        self.app.play_button.invoke()
        pending = self.app._play_after
        self.app.destroy()
        self.app = None
        self.assertNotIn(pending, self.scheduled_callbacks())
        self.root.update()

    def test_invalid_input_preserves_previous_result(self):
        self.app.translate_button.invoke()
        previous = self.app.single_result
        self.app.offset_var.set("không phải số")
        self.app.translate_button.invoke()
        self.assertIs(self.app.single_result, previous)
        self.assertEqual(self.app.playback.physical_address, 1120)
        self.error_dialog.assert_called_once()

    def test_add_update_remove_and_reject_invalid_table_atomically(self):
        self.app.notebook.select(self.app.editor_tab)
        self.app.add_button.invoke()
        self.assertEqual(len(self.app.table.segments), 4)
        self.app.limit_var.set("250")
        self.app.add_button.invoke()
        self.assertEqual(self.app.table.segments[-1].limit, 250)
        self.assertEqual(len(self.app.table.segments), 4)
        previous = self.app.table
        self.app.base_var.set("1000")
        self.app.add_button.invoke()
        self.assertIs(self.app.table, previous)
        self.error_dialog.assert_called_once()
        self.app.segment_tree.selection_set("3")
        self.app.remove_button.invoke()
        self.assertEqual(len(self.app.table.segments), 3)
        self.app._replace_table(SegmentTable([Segment(0, 100, 10)]), "test")
        self.app.segment_tree.selection_set("0")
        self.app.remove_button.invoke()
        self.assertEqual(len(self.app.table.segments), 1)
        self.assertEqual(self.error_dialog.call_count, 2)

    def test_segment_csv_load_and_failed_reload_are_atomic(self):
        valid = self.csv_file("segments.csv", "segment_id,base,limit\n8,5000,50\n")
        with patch("src.gui.filedialog.askopenfilename", return_value=str(valid)):
            self.app.load_segments_button.invoke()
        self.assertEqual(self.app.table.segments[0].segment_id, 8)
        previous = self.app.table
        invalid = self.csv_file("invalid.csv", "segment_id,base\n1,300\n")
        self.assertFalse(self.app.load_segments_path(invalid))
        self.assertIs(self.app.table, previous)
        self.assertEqual(len(self.app.segment_tree.get_children()), 1)
        self.error_dialog.assert_called_once()

    def test_sample_batch_and_export_preserve_trace_and_failures(self):
        self.app.batch_sample_button.invoke()
        self.wait_for_worker()
        self.assertEqual(len(self.app.batch_results), 10)
        self.assertEqual({r.status for r in self.app.batch_results},
                         {"OK", "SEGMENTATION_FAULT", "SEGMENT_NOT_FOUND", "PROTECTION_FAULT"})
        target = Path(self.temp_dir.name) / "results.csv"
        with patch("src.gui.filedialog.asksaveasfilename", return_value=str(target)):
            self.app.export_button.invoke()
        self.wait_for_worker()
        with target.open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0]["physical_address"], "1120")
        self.assertIn("5. Địa chỉ", rows[0]["trace"])
        self.assertEqual(rows[3]["physical_address"], "")
        self.error_dialog.assert_not_called()

    def test_bad_batch_preserves_previous_results(self):
        self.app.batch_sample_button.invoke()
        self.wait_for_worker()
        previous = self.app.batch_results
        invalid = self.csv_file("bad.csv", "segment_id,offset\n0,abc\n")
        self.app.run_batch_path(invalid)
        self.wait_for_worker()
        self.assertIs(self.app.batch_results, previous)
        self.assertEqual(len(self.app.batch_tree.get_children()), 10)
        self.error_dialog.assert_called_once()
        self.assertFalse(self.app.export_button.instate(["disabled"]))

    def test_batch_selected_row_uses_original_table_snapshot(self):
        original = self.app.table
        self.app.run_batch_path(PROJECT_ROOT / "input" / "addresses.csv")
        self.app._replace_table(SegmentTable([Segment(0, 8000, 400)]), "changed")
        self.wait_for_worker()
        self.assertIs(self.app.batch_table, original)
        self.app.batch_tree.selection_set("0")
        self.app.batch_map_button.invoke()
        self.assertIs(self.app.map_canvas.table, original)
        self.assertEqual(self.app.table.segments[0].base, 8000)
        self.assertEqual(self.app.playback.physical_address, 1120)
        self.assertIn("đã chụp", self.app.status_var.get())

    def test_large_batch_limits_widgets_but_exports_all_rows(self):
        count = DISPLAY_LIMIT + 17
        data = self.csv_file("large.csv", "segment_id,offset\n" + "0,120\n" * count)
        self.app.run_batch_path(data)
        self.wait_for_worker()
        self.assertEqual(len(self.app.batch_tree.get_children()), DISPLAY_LIMIT)
        self.assertEqual(len(self.app.batch_results), count)
        target = Path(self.temp_dir.name) / "full.csv"
        with patch("src.gui.filedialog.asksaveasfilename", return_value=str(target)):
            self.app.export_button.invoke()
        self.wait_for_worker()
        with target.open(encoding="utf-8-sig", newline="") as source:
            self.assertEqual(len(list(csv.DictReader(source))), count)

    def test_huge_integer_translation_and_map_do_not_overflow(self):
        huge = 10 ** 400
        self.app._replace_table(SegmentTable([Segment(0, huge, huge)]), "huge values")
        self.app.address_segment_var.set("0")
        self.app.offset_var.set(str(huge - 1))
        self.app.translate_button.invoke()
        self.assertEqual(self.app.playback.physical_address, huge * 2 - 1)
        self.assertTrue(self.app.map_canvas.find_withtag("physical_marker"))
        self.error_dialog.assert_not_called()

    def test_cancelled_dialogs_preserve_state(self):
        previous = self.app.table
        with patch("src.gui.filedialog.askopenfilename", return_value=""):
            self.app.load_segments_button.invoke()
            self.app.batch_run_button.invoke()
        self.assertIs(self.app.table, previous)
        self.assertFalse(self.app._job_running)
        self.error_dialog.assert_not_called()


if __name__ == "__main__":
    unittest.main()
