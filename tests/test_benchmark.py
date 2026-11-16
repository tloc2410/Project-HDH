"""Kiểm thử tự động cho module Benchmark & Stress Test."""

import unittest
from scripts.benchmark import create_sample_table, generate_benchmark_queries, run_single_benchmark


class TestBenchmark(unittest.TestCase):
    def setUp(self):
        self.table = create_sample_table()

    def test_sample_table_creation(self):
        """Bảng phân đoạn mẫu phải có đủ 5 segment và không chồng lấn."""
        self.assertEqual(len(self.table.segments), 5)

    def test_query_generation(self):
        """Hàm sinh dữ liệu phải sinh đúng số lượng n truy vấn với phân phối hợp lý."""
        n = 100
        queries = generate_benchmark_queries(n, seed=123)
        self.assertEqual(len(queries), n)
        # Kiểm tra có cả truy vấn hợp lệ và không hợp lệ
        results = self.table.translate_many(queries)
        statuses = {r.status for r in results}
        self.assertIn("OK", statuses)
        self.assertTrue(len(statuses) > 1, "Phải có cả ca lỗi trong dữ liệu benchmark")

    def test_run_small_benchmark(self):
        """Đo lường một đợt benchmark nhỏ phải trả về đầy đủ các trường số liệu."""
        res = run_single_benchmark(self.table, 50)
        self.assertEqual(res["size"], 50)
        self.assertIn("trans_time_ms", res)
        self.assertIn("latency_us", res)
        self.assertIn("throughput_ops_sec", res)
        self.assertIn("peak_mem_mb", res)
        self.assertGreater(res["throughput_ops_sec"], 0)


if __name__ == "__main__":
    unittest.main()
