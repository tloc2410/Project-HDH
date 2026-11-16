"""Kịch bản Benchmark & Stress Test hiệu năng dịch địa chỉ phân đoạn.

Thực hiện đo đạc:
- Thời gian dịch địa chỉ qua nhiều kích thước dữ liệu (1.000 đến 500.000 truy vấn).
- Tốc độ xử lý (Throughput - ops/sec) và độ trễ trung bình (Latency - µs/op).
- Thời gian nạp và xuất file CSV.
- Đo lường bộ nhớ tiêu thụ (Peak RAM - MB).
- Xuất kết quả ra file CSV và biểu đồ đồ họa (PNG / SVG).

Sử dụng:
    python scripts/benchmark.py
"""

import csv
import os
from pathlib import Path
import random
import sys
import time
import tracemalloc

# Thêm thư mục gốc vào PYTHONPATH để import được src
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.segmentation import LogicalAddress, Segment, SegmentTable
from src.csv_io import save_results


def create_sample_table() -> SegmentTable:
    """Tạo bảng phân đoạn thực tế mô phỏng 5 phân đoạn của tiến trình."""
    segments = [
        Segment(segment_id=0, base=1000, limit=2000, permissions="rx"),   # Code
        Segment(segment_id=1, base=4000, limit=3000, permissions="rw"),   # Data
        Segment(segment_id=2, base=8000, limit=5000, permissions="rw"),   # Heap
        Segment(segment_id=3, base=15000, limit=2000, permissions="rw"),  # Stack
        Segment(segment_id=4, base=18000, limit=1000, permissions="r"),   # Constants
    ]
    return SegmentTable(segments)


def generate_benchmark_queries(n: int, seed: int = 42) -> list[LogicalAddress]:
    """Sinh danh sách n truy vấn ngẫu nhiên mô phỏng hành vi truy xuất bộ nhớ thực tế:
    - 75% Hợp lệ (Normal valid accesses)
    - 10% Lỗi tràn Limit (Segmentation fault: offset >= limit)
    - 5% Lỗi offset âm (Negative offset)
    - 5% Lỗi vi phạm quyền (Protection fault: ghi vào đoạn chỉ đọc)
    - 5% Lỗi không tìm thấy segment (Invalid segment id)
    """
    rng = random.Random(seed)
    queries: list[LogicalAddress] = []
    
    seg_limits = {0: 2000, 1: 3000, 2: 5000, 3: 2000, 4: 1000}
    seg_perms = {0: "rx", 1: "rw", 2: "rw", 3: "rw", 4: "r"}

    for _ in range(n):
        r = rng.random()
        if r < 0.75:
            # 75% ca hợp lệ
            sid = rng.choice([0, 1, 2, 3, 4])
            offset = rng.randint(0, seg_limits[sid] - 1)
            access = rng.choice(list(seg_perms[sid]))
        elif r < 0.85:
            # 10% lỗi tràn limit
            sid = rng.choice([0, 1, 2, 3, 4])
            offset = seg_limits[sid] + rng.randint(0, 1000)
            access = "r"
        elif r < 0.90:
            # 5% lỗi offset âm
            sid = rng.choice([0, 1, 2, 3, 4])
            offset = -rng.randint(1, 500)
            access = "r"
        elif r < 0.95:
            # 5% vi phạm quyền (cố ghi vào đoạn code hoặc hằng số chỉ đọc)
            sid = rng.choice([0, 4])
            offset = rng.randint(0, seg_limits[sid] - 1)
            access = "w"
        else:
            # 5% segment không tồn tại
            sid = rng.randint(10, 99)
            offset = rng.randint(0, 500)
            access = "r"

        queries.append(LogicalAddress(segment_id=sid, offset=offset, access=access))

    return queries


def run_single_benchmark(table: SegmentTable, size: int) -> dict:
    """Đo đạc chi tiết cho một kích thước dữ liệu size."""
    print(f"[*] Đang chuẩn bị {size:,} truy vấn...")
    queries = generate_benchmark_queries(size)

    # Đo thời gian dịch thuần túy (Core Translation)
    tracemalloc.start()
    t_start = time.perf_counter()
    results = table.translate_many(queries)
    t_end = time.perf_counter()
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    trans_time = t_end - t_start
    throughput = size / trans_time if trans_time > 0 else 0
    latency_us = (trans_time / size) * 1_000_000 if size > 0 else 0
    peak_mem_mb = peak_mem / (1024 * 1024)

    # Thống kê trạng thái kết quả
    ok_count = sum(1 for r in results if r.status == "OK")
    seg_fault_count = sum(1 for r in results if r.status == "SEGMENTATION_FAULT")
    prot_fault_count = sum(1 for r in results if r.status == "PROTECTION_FAULT")
    not_found_count = sum(1 for r in results if r.status == "SEGMENT_NOT_FOUND")

    # Đo thời gian xuất file CSV kết quả (I/O performance)
    out_dir = REPO_ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    temp_csv = out_dir / f"temp_perf_{size}.csv"

    t_csv_start = time.perf_counter()
    save_results(temp_csv, results)
    t_csv_end = time.perf_counter()
    csv_time = t_csv_end - t_csv_start

    # Xóa file tạm sau khi đo xong
    if temp_csv.exists():
        temp_csv.unlink()

    return {
        "size": size,
        "trans_time_ms": round(trans_time * 1000, 2),
        "trans_time_s": round(trans_time, 4),
        "latency_us": round(latency_us, 3),
        "throughput_ops_sec": int(throughput),
        "csv_write_time_s": round(csv_time, 3),
        "peak_mem_mb": round(peak_mem_mb, 2),
        "ok_count": ok_count,
        "seg_fault_count": seg_fault_count,
        "prot_fault_count": prot_fault_count,
        "not_found_count": not_found_count,
    }


def draw_svg_charts(records: list[dict], svg_path: Path):
    """Vẽ biểu đồ SVG đẹp mắt, không cần thư viện ngoài."""
    width = 900
    height = 500
    margin_left = 100
    margin_right = 50
    margin_top = 80
    margin_bottom = 80

    chart_w = width - margin_left - margin_right
    chart_h = height - margin_top - margin_bottom

    max_size = max(r["size"] for r in records)
    max_time = max(r["trans_time_ms"] for r in records) * 1.15

    # Tạo các điểm tọa độ
    points = []
    for r in records:
        x = margin_left + (r["size"] / max_size) * chart_w
        y = margin_top + chart_h - (r["trans_time_ms"] / max_time) * chart_h
        points.append((x, y, r["size"], r["trans_time_ms"], r["latency_us"]))

    poly_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y, _, _, _ in points)

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" style="background:#ffffff; font-family:Arial, sans-serif;">',
        f'<!-- Tiêu đề -->',
        f'<text x="{width/2}" y="35" text-anchor="middle" font-size="20" font-weight="bold" fill="#184C78">HIỆU NĂNG DỊCH ĐỊA CHỈ PHÂN ĐOẠN (SEGMENTATION BENCHMARK)</text>',
        f'<text x="{width/2}" y="58" text-anchor="middle" font-size="13" fill="#666666">Đồ thị thực nghiệm chứng minh độ phức tạp O(1) tra cứu và O(N) xử lý chuỗi</text>',

        f'<!-- Khung trục -->',
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top+chart_h}" stroke="#333333" stroke-width="2"/>',
        f'<line x1="{margin_left}" y1="{margin_top+chart_h}" x2="{margin_left+chart_w}" y2="{margin_top+chart_h}" stroke="#333333" stroke-width="2"/>',
    ]

    # Lưới ngang Y
    for i in range(5):
        val = (max_time / 4) * i
        y = margin_top + chart_h - (val / max_time) * chart_h
        svg.append(f'<line x1="{margin_left}" y1="{y:.1f}" x2="{margin_left+chart_w}" y2="{y:.1f}" stroke="#e0e0e0" stroke-dasharray="4"/>')
        svg.append(f'<text x="{margin_left-15}" y="{y+4:.1f}" text-anchor="end" font-size="11" fill="#555555">{val:.0f} ms</text>')

    # Đường đồ thị
    svg.append(f'<polyline points="{poly_pts}" fill="none" stroke="#2980B9" stroke-width="3.5" stroke-linecap="round"/>')

    # Các điểm mốc và nhãn
    for x, y, sz, ms, lat in points:
        svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#E74C3C" stroke="#ffffff" stroke-width="2"/>')
        svg.append(f'<text x="{x:.1f}" y="{y-12:.1f}" text-anchor="middle" font-size="11" font-weight="bold" fill="#184C78">{ms:.1f} ms</text>')
        # Trục X
        lbl = f"{sz//1000}K" if sz >= 1000 else str(sz)
        svg.append(f'<text x="{x:.1f}" y="{margin_top+chart_h+25}" text-anchor="middle" font-size="11" fill="#333333">{lbl}</text>')

    # Nhãn trục
    svg.append(f'<text x="{width/2}" y="{margin_top+chart_h+55}" text-anchor="middle" font-size="13" font-weight="bold" fill="#333333">Số lượng truy vấn địa chỉ (N)</text>')
    svg.append(f'<text transform="rotate(-90)" x="-{margin_top + chart_h/2}" y="30" text-anchor="middle" font-size="13" font-weight="bold" fill="#333333">Thời gian xử lý (ms)</text>')

    svg.append('</svg>')

    with open(svg_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg))


def draw_matplotlib_charts(records: list[dict], png_path: Path):
    """Vẽ biểu đồ chuyên nghiệp bằng matplotlib nếu có sẵn."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    sizes = [r["size"] for r in records]
    times_ms = [r["trans_time_ms"] for r in records]
    latencies = [r["latency_us"] for r in records]
    throughputs = [r["throughput_ops_sec"] / 1000 for r in records]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    # Đồ thị 1: Thời gian thực thi theo kích thước N
    ax1.plot(sizes, times_ms, marker="o", color="#2980B9", linewidth=2.5, markersize=7)
    ax1.set_title("Thời gian xử lý theo kích thước (O(N))", fontsize=12, fontweight="bold", pad=10)
    ax1.set_xlabel("Số lượng truy vấn (N)", fontsize=11)
    ax1.set_ylabel("Thời gian thực thi (ms)", fontsize=11)
    ax1.grid(True, linestyle="--", alpha=0.6)
    for x, y in zip(sizes, times_ms):
        lbl = f"{x//1000}K" if x >= 1000 else str(x)
        ax1.annotate(f"{y:.1f} ms\n({lbl})", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9)

    # Đồ thị 2: Độ trễ trung bình cho 1 phép dịch (Latency)
    ax2.plot(sizes, latencies, marker="s", color="#E74C3C", linewidth=2.5, markersize=7)
    ax2.set_title("Độ trễ trung bình mỗi phép dịch (Chứng minh O(1))", fontsize=12, fontweight="bold", pad=10)
    ax2.set_xlabel("Số lượng truy vấn (N)", fontsize=11)
    ax2.set_ylabel("Độ trễ trung bình (µs / thao tác)", fontsize=11)
    ax2.grid(True, linestyle="--", alpha=0.6)
    for x, y in zip(sizes, latencies):
        ax2.annotate(f"{y:.3f} µs", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9)

    plt.tight_layout()
    plt.savefig(png_path, dpi=300)
    plt.close()
    return True


def main():
    print("=" * 75)
    print(" BỘ KIỂM THỬ VÀ ĐO HIỆU NĂNG HỆ THỐNG PHÂN ĐOẠN (SEGMENTATION BENCHMARK)")
    print("=" * 75)

    table = create_sample_table()
    sizes = [1_000, 10_000, 50_000, 100_000, 250_000, 500_000]

    results: list[dict] = []
    for s in sizes:
        res = run_single_benchmark(table, s)
        results.append(res)
        print(f" -> Hoàn tất {s:>7,}: {res['trans_time_ms']:>8.2f} ms | Độ trễ: {res['latency_us']:>6.3f} µs | Thông lượng: {res['throughput_ops_sec']:>10,} ops/s | RAM: {res['peak_mem_mb']:>5.2f} MB")

    # In bảng tổng hợp
    print("\n" + "=" * 95)
    print(f"{'Kích thước (N)':<15} | {'Thời gian (ms)':<15} | {'Độ trễ (µs/op)':<15} | {'Thông lượng (ops/s)':<20} | {'Peak RAM':<10}")
    print("-" * 95)
    for r in results:
        print(f"{r['size']:<15,}{r['trans_time_ms']:<17.2f}{r['latency_us']:<17.3f}{r['throughput_ops_sec']:<22,}{r['peak_mem_mb']:<6.2f} MB")
    print("=" * 95)

    # Xuất CSV kết quả
    out_dir = REPO_ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    csv_file = out_dir / "benchmark_results.csv"
    with open(csv_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"\n[+] Đã lưu bảng số liệu: {csv_file}")

    # Vẽ biểu đồ SVG và PNG
    report_dir = REPO_ROOT / "report"
    report_dir.mkdir(exist_ok=True)
    svg_file = report_dir / "benchmark_chart.svg"
    draw_svg_charts(results, svg_file)
    print(f"[+] Đã tạo biểu đồ vector SVG: {svg_file}")

    png_file = report_dir / "benchmark_chart.png"
    if draw_matplotlib_charts(results, png_file):
        print(f"[+] Đã tạo biểu đồ chất lượng cao PNG: {png_file}")

    print("\n[V] Hoàn tất quá trình đo hiệu năng thành công!")


if __name__ == "__main__":
    main()
