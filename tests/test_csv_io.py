import csv
from pathlib import Path
import tempfile
import unittest

from src.csv_io import load_addresses, load_segments, save_results
from src.segmentation import LogicalAddress, Segment, SegmentTable


class CsvTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data.csv"

    def write(self, text, encoding="utf-8"):
        self.path.write_text(text, encoding=encoding)
        return self.path

    def test_segments_defaults(self):
        self.assertEqual(load_segments(self.write("segment_id,base,limit\n0,1000,400\n")), [Segment(0, 1000, 400, "rw")])

    def test_addresses_defaults_and_negative_offset(self):
        self.assertEqual(load_addresses(self.write("segment_id,offset\n0,-1\n")), [LogicalAddress(0, -1, "r")])

    def test_bom_supported(self):
        self.assertEqual(load_segments(self.write("segment_id,base,limit,permissions\n0,0,1,x\n", "utf-8-sig"))[0].permissions, "x")

    def test_reordered_headers_and_trimmed_cells(self):
        self.assertEqual(load_addresses(self.write("access,offset,segment_id\n w , 12 , 4 \n")), [LogicalAddress(4, 12, "w")])

    def test_empty_and_header_only(self):
        for data in ("", "\n", "segment_id,offset\n"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                load_addresses(self.write(data))

    def test_invalid_headers(self):
        for data in ("segment_id\n0\n", "segment_id,offset,offset\n0,1,2\n", "segment_id,offset,extra\n0,1,x\n", "segment_id,Offset\n0,1\n"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                load_addresses(self.write(data))

    def test_missing_extra_and_empty_cells(self):
        for row in ("0", "0,1,r,extra", "0,,r", "0,1,"):
            with self.subTest(row=row), self.assertRaisesRegex(ValueError, "Dòng 2"):
                load_addresses(self.write("segment_id,offset,access\n" + row + "\n"))

    def test_invalid_integer_formats(self):
        for value in ("1.5", "1e3", "1_000", "abc", "0x10"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Dòng 2"):
                load_addresses(self.write(f"segment_id,offset\n0,{value}\n"))

    def test_invalid_access_reports_line(self):
        with self.assertRaisesRegex(ValueError, "Dòng 3"):
            load_addresses(self.write("segment_id,offset,access\n0,0,r\n0,1,rw\n"))

    def test_invalid_segment_reports_line(self):
        with self.assertRaisesRegex(ValueError, "Dòng 2"):
            load_segments(self.write("segment_id,base,limit\n0,1000,0\n"))

    def test_duplicate_ids_rejected_on_load(self):
        with self.assertRaisesRegex(ValueError, "trùng"):
            load_segments(self.write("segment_id,base,limit\n0,0,10\n0,20,10\n"))

    def test_overlaps_rejected_on_load(self):
        with self.assertRaisesRegex(ValueError, "chồng lấn"):
            load_segments(self.write("segment_id,base,limit\n0,0,10\n1,9,10\n"))

    def test_unclosed_quote_rejected(self):
        with self.assertRaisesRegex(ValueError, "định dạng"):
            load_addresses(self.write('segment_id,offset\n0,"10\n'))

    def test_invalid_encoding(self):
        self.path.write_bytes(b"segment_id,offset\n0,\xff\n")
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            load_addresses(self.path)

    def test_export_bom_and_multiline_trace_roundtrip(self):
        table = SegmentTable([Segment(0, 1000, 400, "r")])
        results = table.translate_many([LogicalAddress(0, 120), LogicalAddress(0, 400), LogicalAddress(9, 10), LogicalAddress(0, 10, "w")])
        save_results(self.path, iter(results))
        self.assertTrue(self.path.read_bytes().startswith(b"\xef\xbb\xbf"))
        with self.path.open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["physical_address"], "1120")
        self.assertEqual(rows[0]["trace"], "\n".join(results[0].trace))
        self.assertEqual(rows[1]["physical_address"], "")
        self.assertEqual(rows[2]["base"], "")
        self.assertEqual(rows[3]["status"], "PROTECTION_FAULT")
        self.assertEqual(rows[0]["message"], "Dịch địa chỉ thành công.")

    def test_export_empty_results_writes_header(self):
        save_results(self.path, [])
        with self.path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            self.assertIn("status", reader.fieldnames)
            self.assertEqual(list(reader), [])

    def test_sample_results_match_hand_calculated_expected(self):
        root = Path(__file__).resolve().parents[1]
        table = SegmentTable(load_segments(root / "input" / "segments.csv"))
        results = table.translate_many(load_addresses(root / "input" / "addresses.csv"))
        with (root / "input" / "expected_results.csv").open(encoding="utf-8-sig", newline="") as source:
            expected = list(csv.DictReader(source))
        actual = [{"segment_id": str(r.segment_id), "offset": str(r.offset), "access": r.access, "status": r.status, "physical_address": "" if r.physical_address is None else str(r.physical_address)} for r in results]
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
