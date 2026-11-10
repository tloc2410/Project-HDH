"""Playback must reveal only completed stages; Canvas tests use real Tk widgets."""
import math
import tkinter as tk
import unittest

from src.segmentation import LogicalAddress, Segment, SegmentTable
from src.visualization import MemoryCanvas, PALETTE, PipelineCanvas, Playback


def demo_table():
    return SegmentTable([
        Segment(0, 1000, 400, "rx"),
        Segment(1, 2000, 300, "rw"),
        Segment(2, 3000, 100, "w"),
    ])


class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.table = demo_table()
        self.playback = Playback()

    def test_empty_playback_is_waiting_and_navigation_is_clamped(self):
        self.assertFalse(self.playback.complete)
        self.assertEqual(self.playback.total, 0)
        self.assertIsNone(self.playback.physical_address)
        self.assertEqual([stage.state for stage in self.playback.stages()], ["waiting"] * 4)
        self.playback.forward()
        self.playback.backward()
        self.assertEqual(self.playback.visible, 0)

    def test_success_reveals_address_only_at_final_step_and_hides_it_backward(self):
        result = self.table.translate(LogicalAddress(0, 120, "r"))
        self.playback.load(result)
        for visible in range(4):
            self.assertEqual(self.playback.visible, visible)
            self.assertFalse(self.playback.complete)
            self.assertIsNone(self.playback.physical_address)
            self.assertEqual([stage.state for stage in self.playback.stages()],
                             ["pass"] * visible + ["waiting"] * (4 - visible))
            self.playback.forward()
        self.assertTrue(self.playback.complete)
        self.assertEqual(self.playback.physical_address, 1120)
        self.playback.forward()
        self.assertEqual(self.playback.visible, 4)
        self.playback.backward()
        self.assertFalse(self.playback.complete)
        self.assertIsNone(self.playback.physical_address)
        self.assertEqual(self.playback.stages()[-1].state, "waiting")

    def test_failure_and_skipped_stages_are_hidden_until_failure_is_revealed(self):
        cases = [
            (LogicalAddress(99, 0), 1),
            (LogicalAddress(0, -1), 2),
            (LogicalAddress(0, 400), 2),
            (LogicalAddress(0, 10, "w"), 3),
            (LogicalAddress(1, 10, "x"), 3),
            (LogicalAddress(2, 10, "r"), 3),
        ]
        for address, failure_step in cases:
            with self.subTest(address=address):
                self.playback.load(self.table.translate(address))
                for visible in range(failure_step):
                    self.assertEqual([stage.state for stage in self.playback.stages()],
                                     ["pass"] * visible + ["waiting"] * (4 - visible))
                    self.assertIsNone(self.playback.physical_address)
                    self.playback.forward()
                self.assertTrue(self.playback.complete)
                self.assertEqual([stage.state for stage in self.playback.stages()],
                                 ["pass"] * (failure_step - 1) + ["error"]
                                 + ["skipped"] * (4 - failure_step))
                self.assertIsNone(self.playback.physical_address)
                self.playback.backward()
                self.assertEqual([stage.state for stage in self.playback.stages()],
                                 ["pass"] * (failure_step - 1) + ["waiting"] * (5 - failure_step))

    def test_restart_clear_and_loading_another_result_remove_previous_revelation(self):
        self.playback.load(self.table.translate(LogicalAddress(0, 1)), complete=True)
        self.assertEqual(self.playback.physical_address, 1001)
        self.playback.restart()
        self.assertEqual(self.playback.visible, 0)
        self.assertIsNone(self.playback.physical_address)
        for _ in range(10):
            self.playback.backward()
        self.assertEqual(self.playback.visible, 0)
        self.playback.load(self.table.translate(LogicalAddress(0, 0, "w")))
        self.assertEqual([stage.state for stage in self.playback.stages()], ["waiting"] * 4)
        for _ in range(10):
            self.playback.forward()
        self.assertEqual(self.playback.visible, 3)
        self.playback.clear()
        self.assertIsNone(self.playback.result)
        self.assertEqual(self.playback.total, 0)
        self.assertFalse(self.playback.complete)
        self.assertEqual([stage.state for stage in self.playback.stages()], ["waiting"] * 4)


class CanvasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f"Tk display unavailable: {error}") from error
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.table = demo_table()
        self.playback = Playback()
        self.widgets = []
        self.root.geometry("840x500+10+10")

    def tearDown(self):
        for widget in self.widgets:
            widget.destroy()
        self.root.withdraw()

    def canvas(self, kind=MemoryCanvas, height=None):
        widget = kind(self.root)
        if height is not None:
            widget.configure(height=height)
        widget.pack(fill="x")
        self.widgets.append(widget)
        self.root.deiconify()
        self.root.update()
        return widget

    @staticmethod
    def texts(canvas):
        return [canvas.itemcget(item, "text") for item in canvas.find_all()
                if canvas.type(item) == "text"]

    def test_global_physical_marker_appears_only_for_complete_success(self):
        canvas = self.canvas()
        self.playback.load(self.table.translate(LogicalAddress(0, 120)))
        for _ in range(4):
            canvas.draw(self.table, self.playback)
            self.assertFalse(canvas.find_withtag("physical_marker"))
            self.playback.forward()
        canvas.draw(self.table, self.playback)
        self.assertEqual(len(canvas.find_withtag("physical_marker")), 1)
        self.playback.backward()
        canvas.draw(self.table, self.playback)
        self.assertFalse(canvas.find_withtag("physical_marker"))
        self.playback.restart()
        canvas.draw(self.table, self.playback)
        self.assertFalse(canvas.find_withtag("offset_marker"))
        for address in (LogicalAddress(0, -1), LogicalAddress(0, 400),
                        LogicalAddress(0, 1, "w"), LogicalAddress(99, 1)):
            self.playback.load(self.table.translate(address), complete=True)
            canvas.draw(self.table, self.playback)
            self.assertFalse(canvas.find_withtag("physical_marker"))

    def test_offset_marker_is_hidden_before_bounds_and_stays_on_canvas_for_extremes(self):
        canvas = self.canvas()
        for offset in (-10**100, -1, 0, 399, 400, 10**100):
            with self.subTest(offset=offset):
                self.playback.load(self.table.translate(LogicalAddress(0, offset)))
                self.playback.forward()
                canvas.draw(self.table, self.playback)
                self.assertFalse(canvas.find_withtag("offset_marker"))
                self.playback.forward()
                canvas.draw(self.table, self.playback)
                marker, = canvas.find_withtag("offset_marker")
                x0, y0, x1, y1 = canvas.coords(marker)
                self.assertTrue(all(math.isfinite(value) for value in (x0, y0, x1, y1)))
                self.assertGreaterEqual(x0, 0)
                self.assertLessEqual(x1, canvas.winfo_width())
                self.assertGreaterEqual(y0, 0)
                self.assertLessEqual(y1, canvas.winfo_height())

    def test_lookup_includes_selected_segment_outside_first_six(self):
        canvas = self.canvas()
        table = SegmentTable([Segment(index, index * 1000, 100) for index in range(10)])
        self.playback.load(table.translate(LogicalAddress(9, 5)))
        canvas.draw(table, self.playback)
        self.assertNotIn("S9", self.texts(canvas))
        self.playback.forward()
        canvas.draw(table, self.playback)
        self.assertIn("S9", self.texts(canvas))
        self.assertEqual(len(canvas.find_withtag("segment")), 6)
        self.assertTrue(any("6/10 segment" in text for text in self.texts(canvas)))

    def test_pipeline_keeps_errors_and_skipped_stages_hidden_until_revealed(self):
        canvas = self.canvas(PipelineCanvas)
        self.playback.load(self.table.translate(LogicalAddress(0, 1, "w")))
        self.playback.forward()
        self.playback.forward()
        canvas.draw(self.playback)
        self.assertFalse(canvas.find_withtag("error"))
        self.assertFalse(canvas.find_withtag("skipped"))
        self.playback.forward()
        canvas.draw(self.playback)
        self.assertEqual(len(canvas.find_withtag("error")), 1)
        self.assertEqual(len(canvas.find_withtag("skipped")), 1)
        self.assertEqual(canvas.itemcget(canvas.find_withtag("error")[0], "fill"), PALETTE["error_bg"])
        self.playback.backward()
        canvas.draw(self.playback)
        self.assertFalse(canvas.find_withtag("error"))
        self.assertFalse(canvas.find_withtag("skipped"))

    def test_resize_redraws_memory_marker_and_pipeline_without_losing_state(self):
        memory = self.canvas()
        pipeline = self.canvas(PipelineCanvas)
        self.playback.load(self.table.translate(LogicalAddress(0, 120)), complete=True)
        memory.draw(self.table, self.playback)
        pipeline.draw(self.playback)
        first_marker_x = memory.coords(memory.find_withtag("physical_marker")[0])[0]
        first_last_stage_x = pipeline.coords(pipeline.find_withtag("translation")[0])[2]
        self.root.geometry("1100x500+10+10")
        self.root.update()
        self.assertGreater(memory.coords(memory.find_withtag("physical_marker")[0])[0], first_marker_x)
        self.assertGreater(pipeline.coords(pipeline.find_withtag("translation")[0])[2], first_last_stage_x)
        self.assertEqual(len(pipeline.find_withtag("pass")), 4)
        self.assertEqual(len(memory.find_withtag("physical_marker")), 1)

    def test_six_global_rows_do_not_overlap_zoom_heading_at_small_height(self):
        canvas = self.canvas(height=190)
        table = SegmentTable([Segment(index, index * 1000, 100) for index in range(6)])
        self.playback.load(table.translate(LogicalAddress(5, 50)), complete=True)
        canvas.draw(table, self.playback)
        row_bottom = max(canvas.coords(item)[3] for item in canvas.find_withtag("segment"))
        zoom_heading, = [item for item in canvas.find_all() if canvas.type(item) == "text"
                         and canvas.itemcget(item, "text").startswith("PHÓNG TO")]
        self.assertLess(row_bottom, canvas.bbox(zoom_heading)[1])


if __name__ == "__main__":
    unittest.main()
