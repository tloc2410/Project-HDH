"""Các giá trị kỳ vọng được tính tay, không gọi lại thuật toán để làm oracle."""

from dataclasses import FrozenInstanceError
import unittest

from src.segmentation import LogicalAddress, Segment, SegmentTable, TranslationResult


class TranslationTests(unittest.TestCase):
    def setUp(self):
        self.table = SegmentTable([Segment(0, 1000, 400, "rx"), Segment(1, 2000, 300)])

    def test_normal_translation(self):
        result = self.table.translate(LogicalAddress(0, 120))
        self.assertEqual((result.status, result.physical_address), ("OK", 1120))
        self.assertEqual((result.base, result.limit), (1000, 400))
        self.assertEqual(len(result.trace), 5)
        self.assertIn("1120", result.trace[-1])

    def test_lower_boundary(self):
        self.assertEqual(self.table.translate(LogicalAddress(0, 0)).physical_address, 1000)

    def test_last_valid_offset(self):
        self.assertEqual(self.table.translate(LogicalAddress(0, 399)).physical_address, 1399)

    def test_offset_equal_limit_faults(self):
        result = self.table.translate(LogicalAddress(0, 400))
        self.assertEqual(result.status, "SEGMENTATION_FAULT")
        self.assertIsNone(result.physical_address)

    def test_offset_above_limit_faults(self):
        self.assertEqual(self.table.translate(LogicalAddress(0, 999)).status, "SEGMENTATION_FAULT")

    def test_negative_offset_faults(self):
        self.assertEqual(self.table.translate(LogicalAddress(0, -1)).status, "SEGMENTATION_FAULT")

    def test_missing_segment_has_no_base_limit_or_physical(self):
        result = self.table.translate(LogicalAddress(99, 0))
        self.assertEqual(result.status, "SEGMENT_NOT_FOUND")
        self.assertEqual((result.base, result.limit, result.physical_address), (None, None, None))

    def test_execute_allowed(self):
        self.assertEqual(self.table.translate(LogicalAddress(0, 10, "x")).physical_address, 1010)

    def test_write_denied_for_read_execute(self):
        result = self.table.translate(LogicalAddress(0, 10, "w"))
        self.assertEqual(result.status, "PROTECTION_FAULT")
        self.assertIsNone(result.physical_address)

    def test_execute_denied_for_read_write(self):
        self.assertEqual(self.table.translate(LogicalAddress(1, 10, "x")).status, "PROTECTION_FAULT")

    def test_bounds_checked_before_permissions(self):
        self.assertEqual(self.table.translate(LogicalAddress(0, 400, "w")).status, "SEGMENTATION_FAULT")

    def test_batch_preserves_input_order_and_accepts_generator(self):
        addresses = (LogicalAddress(s, o, a) for s, o, a in [(1, 50, "w"), (0, 400, "r"), (0, 0, "x")])
        results = self.table.translate_many(addresses)
        self.assertEqual([(r.status, r.physical_address) for r in results], [("OK", 2050), ("SEGMENTATION_FAULT", None), ("OK", 1000)])

    def test_empty_address_batch(self):
        self.assertEqual(self.table.translate_many([]), [])

    def test_sparse_segment_ids(self):
        table = SegmentTable([Segment(400, 0, 1)])
        self.assertEqual(table.translate(LogicalAddress(400, 0)).physical_address, 0)

    def test_large_integers_do_not_overflow(self):
        table = SegmentTable([Segment(0, 10**30, 10)])
        self.assertEqual(table.translate(LogicalAddress(0, 9)).physical_address, 1000000000000000000000000000009)

    def test_result_is_immutable(self):
        result = self.table.translate(LogicalAddress(0, 0))
        with self.assertRaises(FrozenInstanceError):
            result.status = "changed"

    def test_non_address_rejected(self):
        with self.assertRaises(ValueError):
            self.table.translate((0, 0))

    def test_successful_visualization_runs_all_four_stages(self):
        result = self.table.translate(LogicalAddress(0, 120))
        self.assertEqual([step.stage for step in result.steps],
                         ["lookup", "bounds", "permission", "translation"])
        self.assertTrue(all(step.success for step in result.steps))
        self.assertIn("1120", result.steps[-1].description)
        self.assertTrue(all(step.title and step.description for step in result.steps))

    def test_visualization_stops_at_first_failure(self):
        cases = [
            (LogicalAddress(99, -1, "w"), ["lookup"]),
            (LogicalAddress(0, -1, "w"), ["lookup", "bounds"]),
            (LogicalAddress(0, 400, "w"), ["lookup", "bounds"]),
            (LogicalAddress(0, 10, "w"), ["lookup", "bounds", "permission"]),
        ]
        for address, stages in cases:
            with self.subTest(address=address):
                result = self.table.translate(address)
                self.assertEqual([step.stage for step in result.steps], stages)
                self.assertFalse(result.steps[-1].success)
                self.assertTrue(all(step.success for step in result.steps[:-1]))
                self.assertIsNone(result.physical_address)

    def test_permission_matrix(self):
        for permissions in ("r", "w", "x", "rw", "rx", "wx", "rwx"):
            table = SegmentTable([Segment(0, 100, 10, permissions)])
            for access in "rwx":
                with self.subTest(permissions=permissions, access=access):
                    result = table.translate(LogicalAddress(0, 5, access))
                    expected = ("OK", 105) if access in permissions else ("PROTECTION_FAULT", None)
                    self.assertEqual((result.status, result.physical_address), expected)

    def test_visualization_steps_are_immutable(self):
        step = self.table.translate(LogicalAddress(0, 0)).steps[0]
        with self.assertRaises(FrozenInstanceError):
            step.success = False

    def test_legacy_result_can_be_constructed_without_visualization_steps(self):
        result = TranslationResult(0, 0, "r", 1000, 400, "OK", 1000, "OK", ("done",))
        self.assertEqual(result.steps, ())


class ValidationTests(unittest.TestCase):
    def test_invalid_segment_fields(self):
        cases = [(-1, 0, 1), (0, -1, 1), (0, 0, 0), (0, 0, -1), (True, 0, 1), (0, 1.5, 1), (0, 0, "1")]
        for values in cases:
            with self.subTest(values=values), self.assertRaises(ValueError):
                Segment(*values)

    def test_invalid_permissions(self):
        for permissions in ("", "rr", "read", "R", None, 1):
            with self.subTest(permissions=permissions), self.assertRaises(ValueError):
                Segment(0, 0, 1, permissions)

    def test_all_valid_permission_combinations(self):
        for permissions in ("r", "w", "x", "rw", "rx", "wx", "rwx", "xr"):
            with self.subTest(permissions=permissions):
                self.assertEqual(Segment(0, 0, 1, permissions).permissions, permissions)

    def test_invalid_address_fields(self):
        cases = [(-1, 0, "r"), (0, 0.5, "r"), (False, 0, "r"), (0, True, "r"), (0, 0, "rw"), (0, 0, ""), (0, 0, None)]
        for values in cases:
            with self.subTest(values=values), self.assertRaises(ValueError):
                LogicalAddress(*values)

    def test_empty_table_rejected(self):
        with self.assertRaisesRegex(ValueError, "ít nhất"):
            SegmentTable([])

    def test_duplicate_ids_rejected(self):
        with self.assertRaisesRegex(ValueError, "trùng"):
            SegmentTable([Segment(2, 0, 10), Segment(2, 10, 10)])

    def test_overlap_rejected_independent_of_input_order(self):
        with self.assertRaisesRegex(ValueError, "chồng lấn"):
            SegmentTable([Segment(1, 9, 5), Segment(0, 0, 10)])

    def test_containment_overlap_rejected(self):
        with self.assertRaises(ValueError):
            SegmentTable([Segment(0, 0, 100), Segment(1, 10, 5)])

    def test_adjacent_segments_valid_and_input_order_preserved(self):
        segments = [Segment(1, 10, 5), Segment(0, 0, 10)]
        table = SegmentTable(iter(segments))
        self.assertEqual(table.segments, tuple(segments))

    def test_non_segment_rejected(self):
        with self.assertRaises(ValueError):
            SegmentTable([{"segment_id": 0, "base": 0, "limit": 1}])


if __name__ == "__main__":
    unittest.main()
