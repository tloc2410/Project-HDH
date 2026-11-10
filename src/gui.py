"""Vietnamese Tkinter front end for the segmentation simulator.

This module and visualization.py use Tk. Batch address CSV parsing,
translation and result export run outside the UI thread; widgets are
updated on the main thread.
"""
from __future__ import annotations

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .csv_io import load_addresses, load_segments, save_results
from .segmentation import LogicalAddress, Segment, SegmentTable, TranslationResult
from .visualization import MemoryCanvas, PipelineCanvas, Playback, compact


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DISPLAY_LIMIT = 1000
COLORS = {
    "background": "#edf2f7", "surface": "#ffffff", "navy": "#152b45",
    "text": "#233a50", "muted": "#627589", "teal": "#087f83",
    "light_teal": "#e2f4f1", "red": "#b53443", "light_red": "#fcebee",
    "border": "#dae3ec", "blue": "#467bb5",
}
ACCESS_NAMES = {"Đọc (r)": "r", "Ghi (w)": "w", "Thực thi (x)": "x"}
STATUS_NAMES = {
    "OK": "Hợp lệ", "SEGMENT_NOT_FOUND": "Không có segment",
    "SEGMENTATION_FAULT": "Vượt giới hạn", "PROTECTION_FAULT": "Không đủ quyền",
}


def short_number(value: int | None, max_length: int = 22) -> str:
    """Keep huge integer labels inside the layout; exact values remain in CSV."""
    if value is None:
        return "—"
    raw = str(value)
    if len(raw) <= max_length:
        return raw
    return f"{raw[:10]}…{raw[-6:]} ({len(raw.lstrip('-'))} chữ số)"


class SegmentationApp(ttk.Frame):
    """Desktop application; constructing it never starts mainloop."""

    def __init__(self, master: tk.Tk):
        super().__init__(master, style="App.TFrame")
        self.master = master
        self.table = SegmentTable([Segment(0, 1000, 400, "rx"),
                                   Segment(1, 2000, 300, "rw"),
                                   Segment(2, 3000, 500, "rw")])
        self.single_result: TranslationResult | None = None
        self.batch_table = self.table
        self.batch_results: list[TranslationResult] = []
        self.trace_steps: tuple[str, ...] = ()
        self.trace_visible = 0
        self.playback = Playback()
        self._play_after: str | None = None
        self._map_table = self.table
        self._map_result: TranslationResult | None = None
        self._map_after: str | None = None
        self._job_after: str | None = None
        self._job_queue: queue.Queue = queue.Queue()
        self._job_callback: Callable | None = None
        self._job_running = False
        self._configure_style()
        master.title("Project-HDH · Trực quan hóa Segmentation")
        # Tk reports logical pixels on Windows with display scaling enabled.
        # Reserve room for the title bar and taskbar instead of assuming a
        # 1080-pixel physical display can accommodate an 850-pixel Tk window.
        width = min(1180, max(640, master.winfo_screenwidth() - 80))
        height = min(760, max(480, master.winfo_screenheight() - 140))
        master.geometry(f"{width}x{height}+24+24")
        master.minsize(min(1000, width), min(700, height))
        master.configure(background=COLORS["background"])
        self.pack(fill="both", expand=True)
        self._build_header()
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(10, 8))
        self.simulator_tab = ttk.Frame(self.notebook, padding=10, style="App.TFrame")
        self.editor_tab = ttk.Frame(self.notebook, padding=10, style="App.TFrame")
        self.batch_tab = ttk.Frame(self.notebook, padding=10, style="App.TFrame")
        self.help_tab = ttk.Frame(self.notebook, padding=10, style="App.TFrame")
        self.notebook.add(self.simulator_tab, text="  01  Dịch địa chỉ  ")
        self.notebook.add(self.editor_tab, text="  02  Sửa bảng segment  ")
        self.notebook.add(self.batch_tab, text="  03  Xử lý CSV  ")
        self.notebook.add(self.help_tab, text="  04  Hướng dẫn  ")
        self._build_simulator()
        self._build_batch()
        self._build_help()
        self.status_var = tk.StringVar(value="Sẵn sàng. Dữ liệu mẫu đã được nạp.")
        self.status_label = ttk.Label(self, textvariable=self.status_var, style="Foot.TLabel")
        self.status_label.pack(side="bottom", fill="x", padx=24, pady=(0, 12), before=self.notebook)
        self.load_sample()

    def destroy(self) -> None:
        """Cancel pending Tk callbacks when the window or a test closes."""
        for callback in (self._map_after, self._job_after, self._play_after):
            if callback is not None:
                self.after_cancel(callback)
        self._map_after = self._job_after = self._play_after = None
        super().destroy()

    def _configure_style(self) -> None:
        style = ttk.Style(self.master)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background=COLORS["surface"],
                        foreground=COLORS["text"])
        style.configure("App.TFrame", background=COLORS["background"])
        style.configure("Card.TFrame", background=COLORS["surface"])
        style.configure("Title.TLabel", font=("Segoe UI", 13, "bold"))
        style.configure("Sub.TLabel", foreground=COLORS["muted"], font=("Segoe UI", 9))
        style.configure("Foot.TLabel", background=COLORS["background"],
                        foreground=COLORS["muted"], font=("Segoe UI", 9))
        style.configure("TNotebook", background=COLORS["background"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 9), background="#dfe8f0")
        style.map("TNotebook.Tab", background=[("selected", COLORS["surface"])],
                  foreground=[("selected", COLORS["teal"])])
        style.configure("TButton", padding=(10, 7), borderwidth=1)
        style.configure("Accent.TButton", background=COLORS["teal"], foreground="white")
        style.map("Accent.TButton", background=[("active", "#096b70"),
                  ("disabled", "#95b5b6")], foreground=[("disabled", "#f4f7f8")])
        style.configure("Treeview", rowheight=27, fieldbackground=COLORS["surface"],
                        borderwidth=0, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#eaf0f5", padding=(6, 8),
                        font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#d0e9ef")],
                  foreground=[("selected", COLORS["navy"])])
        style.configure("TEntry", padding=5)
        style.configure("TCombobox", padding=5)

    def _build_header(self) -> None:
        header = tk.Frame(self, background=COLORS["navy"], padx=24, pady=10)
        header.pack(fill="x")
        tk.Label(header, text="Trực quan hóa phân đoạn bộ nhớ",
                 font=("Segoe UI", 19, "bold"), foreground="white",
                 background=COLORS["navy"]).pack(anchor="w", pady=(3, 4))
        tk.Label(header, text="Project-HDH   /   Tra segment → Giới hạn → Quyền r/w/x → Địa chỉ vật lý",
                 font=("Segoe UI", 10), foreground="#bed1e3",
                 background=COLORS["navy"]).pack(anchor="w")

    @staticmethod
    def _card(parent, title: str, subtitle: str) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=10, style="Card.TFrame")
        ttk.Label(frame, text=title, style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text=subtitle, style="Sub.TLabel", wraplength=520).pack(
            anchor="w", pady=(3, 10))
        return frame

    @staticmethod
    def _tree(parent, columns: tuple, headings: tuple, widths: tuple, height: int):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=height,
                            selectmode="browse")
        for column, label, width in zip(columns, headings, widths):
            tree.heading(column, text=label)
            tree.column(column, width=width, minwidth=55, anchor="center")
        vertical = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    def _build_simulator(self) -> None:
        area = self.simulator_tab
        area.columnconfigure(0, weight=4, uniform="split")
        area.columnconfigure(1, weight=5, uniform="split")
        area.rowconfigure(0, weight=1)
        left = ttk.Frame(area, style="App.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        right = ttk.Frame(area, style="App.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        segments = self._card(left, "Bảng segment", "Limit là độ dài. Offset hợp lệ: 0 ≤ offset < limit.")
        segments.pack(fill="both", expand=True)
        toolbar = ttk.Frame(segments)
        toolbar.pack(fill="x", pady=(0, 8))
        self.sample_button = ttk.Button(toolbar, text="Nạp mẫu", command=self.load_sample)
        self.sample_button.pack(side="left")
        self.load_segments_button = ttk.Button(toolbar, text="Mở segments.csv", command=self.open_segments)
        self.load_segments_button.pack(side="left", padx=6)
        self.segment_count_var = tk.StringVar()
        ttk.Label(toolbar, textvariable=self.segment_count_var, style="Sub.TLabel").pack(side="right")
        self.segment_tree = self._tree(segments, ("id", "base", "limit", "rights"),
            ("Segment", "Base", "Limit", "Quyền"), (75, 105, 95, 55), 3)
        self.segment_tree.bind("<<TreeviewSelect>>", self._select_segment)
        editor = self._card(self.editor_tab, "Chỉnh sửa bảng segment",
            "Chọn dòng ở tab Dịch địa chỉ để nạp thông số. ID đã có sẽ được cập nhật; ID mới được thêm.")
        editor.pack(fill="x")
        form = ttk.Frame(editor)
        form.pack(fill="x", pady=(8, 0))
        self.segment_id_var = tk.StringVar(value="3")
        self.base_var = tk.StringVar(value="4000")
        self.limit_var = tk.StringVar(value="200")
        self.permissions_var = tk.StringVar(value="rw")
        fields = (("ID", self.segment_id_var), ("Base", self.base_var),
                  ("Limit", self.limit_var), ("Quyền", self.permissions_var))
        for column, (label, variable) in enumerate(fields):
            form.columnconfigure(column, weight=1)
            ttk.Label(form, text=label, style="Sub.TLabel").grid(row=0, column=column, sticky="w")
            widget = (ttk.Combobox(form, textvariable=variable, values=("r", "rw", "rx", "rwx", "w", "wx", "x"),
                                  state="readonly", width=5) if column == 3 else
                      ttk.Entry(form, textvariable=variable, width=8))
            widget.grid(row=1, column=column, sticky="ew", padx=(0, 5))
        actions = ttk.Frame(editor)
        actions.pack(fill="x", pady=(8, 0))
        self.add_button = ttk.Button(actions, text="Thêm / cập nhật", command=self.upsert_segment)
        self.add_button.pack(side="left")
        self.remove_button = ttk.Button(actions, text="Xóa segment chọn", command=self.remove_segment)
        self.remove_button.pack(side="left", padx=6)
        ttk.Label(editor, text="Bảng mới được áp dụng cho các lần dịch tiếp theo. Kết quả CSV cũ giữ bảng đã chụp.",
                  style="Sub.TLabel", wraplength=900).pack(anchor="w", pady=(12, 0))

        address = self._card(left, "Địa chỉ logic", "Chọn segment, độ lệch và thao tác truy cập.")
        address.pack(side="bottom", fill="x", pady=(12, 0), before=segments)
        addr_form = ttk.Frame(address)
        addr_form.pack(fill="x")
        self.address_segment_var = tk.StringVar(value="0")
        self.offset_var = tk.StringVar(value="120")
        self.access_var = tk.StringVar(value="Đọc (r)")
        for column, (label, variable) in enumerate((("Segment ID", self.address_segment_var),
                ("Offset", self.offset_var), ("Thao tác", self.access_var))):
            addr_form.columnconfigure(column, weight=1)
            ttk.Label(addr_form, text=label, style="Sub.TLabel").grid(row=0, column=column, sticky="w")
            widget = (ttk.Combobox(addr_form, textvariable=variable, values=tuple(ACCESS_NAMES),
                                  state="readonly", width=13) if column == 2 else
                      ttk.Entry(addr_form, textvariable=variable, width=9))
            widget.grid(row=1, column=column, sticky="ew", padx=(0, 6))
            if column != 2:
                widget.bind("<Return>", lambda event: self.translate_single())
        buttons = ttk.Frame(address)
        buttons.pack(fill="x", pady=(10, 0))
        self.translate_button = ttk.Button(buttons, text="Dịch địa chỉ", style="Accent.TButton",
                                           command=self.translate_single)
        self.translate_button.pack(side="left")
        self.step_button = ttk.Button(buttons, text="Từng bước", command=lambda: self.translate_single(step=True))
        self.step_button.pack(side="left", padx=6)
        self.play_button = ttk.Button(buttons, text="▶ Tự chạy", command=self.toggle_play)
        self.play_button.pack(side="left")
        self.speed_var = tk.StringVar(value="1 giây")
        ttk.Combobox(buttons, textvariable=self.speed_var,
                     values=("0,5 giây", "1 giây", "2 giây"), state="readonly", width=7).pack(side="left", padx=(6, 0))

        demo = ttk.Frame(address)
        demo.pack(fill="x", pady=(10, 0))
        self.scenarios = {
            "Hợp lệ · đọc": (0, 120, "Đọc (r)"),
            "Hợp lệ · ghi": (1, 50, "Ghi (w)"),
            "Hợp lệ · thực thi": (0, 0, "Thực thi (x)"),
            "Biên cuối · limit − 1": (0, 399, "Đọc (r)"),
            "Lỗi · offset = limit": (0, 400, "Đọc (r)"),
            "Lỗi · offset âm": (0, -1, "Đọc (r)"),
            "Lỗi · quyền ghi": (0, 100, "Ghi (w)"),
            "Lỗi · quyền thực thi": (1, 20, "Thực thi (x)"),
            "Lỗi · thiếu segment": (9, 10, "Đọc (r)"),
        }
        self.scenario_var = tk.StringVar(value=next(iter(self.scenarios)))
        ttk.Combobox(demo, textvariable=self.scenario_var, values=tuple(self.scenarios),
                     state="readonly", width=23).pack(side="left", fill="x", expand=True)
        self.scenario_button = ttk.Button(demo, text="Nạp tình huống", command=self.load_scenario)
        self.scenario_button.pack(side="left", padx=(6, 0))
        ttk.Label(address, text="Tình huống mẫu sẽ nạp lại bảng 3 segment ban đầu.",
                  style="Sub.TLabel", wraplength=390).pack(anchor="w", pady=(5, 0))

        result = ttk.Frame(right, padding=10, style="Card.TFrame")
        result.pack(fill="x")
        ttk.Label(result, text="Các bước dịch địa chỉ", style="Title.TLabel").pack(anchor="w")
        self.pipeline_canvas = PipelineCanvas(result)
        self.pipeline_canvas.pack(fill="x")
        self.result_box = tk.Frame(result, background=COLORS["light_teal"], padx=10, pady=6)
        self.result_box.pack(fill="x")
        self.result_title = tk.Label(self.result_box, text="Sẵn sàng mô phỏng", anchor="w",
            font=("Segoe UI", 12, "bold"), background=COLORS["light_teal"], foreground=COLORS["teal"])
        self.result_title.pack(fill="x")
        self.result_detail = tk.Label(self.result_box, text="Nhập địa chỉ logic và bấm Dịch địa chỉ.",
            anchor="w", justify="left", wraplength=510, font=("Segoe UI", 10),
            background=COLORS["light_teal"], foreground=COLORS["text"])
        self.result_detail.pack(fill="x", pady=(4, 0))
        self.result_box.bind("<Configure>", lambda e: self.result_detail.configure(wraplength=max(100, e.width - 24)))
        trace_head = ttk.Frame(result)
        trace_head.pack(fill="x", pady=(6, 4))
        self.trace_label_var = tk.StringVar(value="Các bước xử lý")
        ttk.Label(trace_head, textvariable=self.trace_label_var, style="Sub.TLabel").pack(side="left")
        self.next_button = ttk.Button(trace_head, text="Bước tiếp →", command=self.next_step, state="disabled")
        self.next_button.pack(side="right")
        self.previous_button = ttk.Button(trace_head, text="← Lùi", command=self.previous_step, state="disabled")
        self.previous_button.pack(side="right", padx=4)
        self.restart_button = ttk.Button(trace_head, text="Chạy lại", command=self.restart_simulation, state="disabled")
        self.restart_button.pack(side="right")
        trace_frame = ttk.Frame(result)
        trace_frame.pack(fill="x")
        self.trace_text = tk.Text(trace_frame, height=2, wrap="word", relief="flat", padx=9, pady=4,
            font=("Segoe UI", 10), background="#f5f8fb", foreground=COLORS["text"], state="disabled")
        trace_scroll = ttk.Scrollbar(trace_frame, orient="vertical", command=self.trace_text.yview)
        self.trace_text.configure(yscrollcommand=trace_scroll.set)
        self.trace_text.pack(side="left", fill="both", expand=True)
        trace_scroll.pack(side="right", fill="y")

        map_card = ttk.Frame(right, padding=12, style="Card.TFrame")
        map_card.pack(fill="both", expand=True, pady=(12, 0))
        self.map_canvas = MemoryCanvas(map_card)
        self.map_canvas.pack(fill="both", expand=True)

    def _build_batch(self) -> None:
        card = self._card(self.batch_tab, "Dịch danh sách địa chỉ từ CSV",
            "Dùng một bản chụp bảng segment tại lúc chạy. Kết quả CSV được xuất đầy đủ.")
        card.pack(fill="both", expand=True)
        toolbar = ttk.Frame(card)
        toolbar.pack(fill="x", pady=(0, 12))
        self.batch_run_button = ttk.Button(toolbar, text="Mở addresses.csv và chạy",
            style="Accent.TButton", command=self.open_addresses)
        self.batch_run_button.pack(side="left")
        self.batch_sample_button = ttk.Button(toolbar, text="Chạy bộ địa chỉ mẫu", command=self.run_sample_batch)
        self.batch_sample_button.pack(side="left", padx=8)
        self.export_button = ttk.Button(toolbar, text="Xuất kết quả CSV", command=self.export_results,
                                        state="disabled")
        self.export_button.pack(side="right")
        self.progress = ttk.Progressbar(card, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 8))
        self.batch_summary_var = tk.StringVar(value="Chưa chạy dữ liệu. Chọn CSV hoặc chạy bộ mẫu.")
        ttk.Label(card, textvariable=self.batch_summary_var, wraplength=1000).pack(anchor="w", pady=(0, 10))
        self.batch_tree = self._tree(card, ("row", "segment", "offset", "access", "status", "physical"),
            ("Dòng", "Segment", "Offset", "Thao tác", "Kết quả", "Địa chỉ vật lý"),
            (55, 100, 145, 85, 190, 180), 10)
        self.batch_tree.tag_configure("ok", foreground=COLORS["teal"])
        self.batch_tree.tag_configure("error", foreground=COLORS["red"])
        self.batch_tree.bind("<<TreeviewSelect>>", self._select_batch_result)
        ttk.Label(card, text=f"Hiển thị tối đa {DISPLAY_LIMIT:,} dòng đầu. Chọn một dòng để xem chi tiết bên dưới.",
                  style="Sub.TLabel").pack(anchor="w", pady=(8, 5))
        detail_frame = ttk.Frame(card)
        detail_frame.pack(fill="x")
        self.batch_detail = tk.Text(detail_frame, height=6, wrap="word", relief="flat", padx=12, pady=8,
            font=("Segoe UI", 10), background="#f5f8fb", foreground=COLORS["text"], state="disabled")
        scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=self.batch_detail.yview)
        self.batch_detail.configure(yscrollcommand=scroll.set)
        self.batch_detail.pack(side="left", fill="x", expand=True)
        scroll.pack(side="right", fill="y")
        self.batch_map_button = ttk.Button(card, text="Xem dòng chọn trên sơ đồ →", command=self.show_batch_map,
                                          state="disabled")
        self.batch_map_button.pack(anchor="e", pady=(8, 0))

    def _build_help(self) -> None:
        card = self._card(self.help_tab, "Bắt đầu trong 3 phút", "Mô hình học tập về phân đoạn và dịch địa chỉ logic.")
        card.pack(fill="both", expand=True)
        body = tk.Text(card, wrap="word", relief="flat", font=("Segoe UI", 11),
                       foreground=COLORS["text"], padx=8, pady=8)
        scroll = ttk.Scrollbar(card, command=body.yview)
        body.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        body.pack(fill="both", expand=True)
        text = """1. KHÁM PHÁ BẢNG SEGMENT
Mỗi dòng gồm ID, base (địa chỉ bắt đầu), limit (độ dài) và quyền r/w/x.
Chọn dòng rồi sang tab “Sửa bảng segment” để sửa thông số và bấm “Thêm / cập nhật”.
ID có sẵn sẽ được cập nhật; ID mới sẽ được thêm.
Nút “Nạp mẫu” đưa bảng về 3 segment ban đầu. Có thể nhập bảng từ CSV.

2. DỊCH MỘT ĐỊA CHỈ
Địa chỉ logic gồm (segment ID, offset). Chọn thao tác Đọc, Ghi hoặc Thực thi.
Chương trình tra segment → kiểm tra 0 ≤ offset < limit → kiểm tra quyền → tính base + offset.
“Dịch địa chỉ” hiển thị toàn bộ kết quả. “Từng bước” bắt đầu từ bước 0.
Dùng “Bước tiếp →”, “← Lùi”, “Chạy lại” hoặc “Tự chạy / Tạm dừng” để điều khiển.
Kết quả và dấu địa chỉ vật lý chỉ hiện sau bước cộng base + offset thành công.

Với dữ liệu mẫu:
• Segment 0, offset 120, Đọc → 1000 + 120 = 1120.
• Segment 0, offset 399 → địa chỉ cuối cùng hợp lệ: 1399.
• Segment 0, offset 400 → SEGMENTATION_FAULT (không có địa chỉ vật lý).
• Segment 9, offset 10 → SEGMENT_NOT_FOUND.
• Segment 0, offset 100, Ghi → PROTECTION_FAULT vì segment chỉ có quyền đọc và thực thi.

3. CHẠY NHIỀU ĐỊA CHỈ
Sang tab “Xử lý CSV”, mở addresses.csv hoặc bấm “Chạy bộ địa chỉ mẫu”.
Chọn kết quả để xem trace; có thể đưa dòng chọn lên sơ đồ ở tab Dịch địa chỉ.
Bảng lớn chỉ hiển thị 1.000 dòng đầu để giữ giao diện phản hồi. Xuất CSV vẫn gồm mọi kết quả.
Bảng segment được chụp tại lúc chạy; sửa bảng sau đó không thay đổi kết quả cũ.

ĐỊNH DẠNG CSV
segments.csv: segment_id,base,limit,permissions
Ví dụ: 0,1000,400,rw
addresses.csv: segment_id,offset,access
Ví dụ: 0,120,r
Cột permissions và access là tùy chọn; mặc định lần lượt là rw và r.
Thư mục input/ trong dự án có dữ liệu mẫu. CSV đầu vào dùng số nguyên hệ thập phân.

HIỂU SƠ ĐỒ
Các thanh được đặt theo địa chỉ vật lý và dùng cùng một thang từ 0 tới địa chỉ cuối cùng.
Base là đầu thanh; địa chỉ cuối là base + limit − 1. Dấu màu chỉ địa chỉ truy cập hợp lệ.
Vùng nhỏ hơn độ phân giải màn hình được vẽ rộng ít nhất 2 px để vẫn nhìn thấy.
Tối đa 6 segment hiện trên sơ đồ; segment đang dịch luôn được đưa vào nếu tồn tại.
Nhãn quá dài được rút gọn; CSV xuất và trace lưu giá trị đầy đủ.

GIẢ ĐỊNH CỦA MÔ HÌNH
Đây là trình mô phỏng, không đọc hoặc ghi bộ nhớ thật của máy.
Quyền r/w/x là phần mở rộng để minh họa bảo vệ; truy cập bị từ chối không sinh địa chỉ vật lý.
Một bảng đang xét cho một không gian địa chỉ, có ít nhất một segment và không có vùng chồng lấn.
Không mô phỏng paging, swap hay kernel thật.
Xem README và report/visualization.md để đọc thiết kế và kịch bản demo.
"""
        body.insert("1.0", text)
        body.configure(state="disabled")

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _error(self, message: str) -> None:
        self._set_status(message)
        messagebox.showerror("Không thể thực hiện", message, parent=self.master)

    def _replace_table(self, table: SegmentTable, source: str) -> None:
        self.table = table
        self.segment_tree.delete(*self.segment_tree.get_children())
        for index, segment in enumerate(table.segments[:DISPLAY_LIMIT]):
            self.segment_tree.insert("", "end", iid=str(index), values=(short_number(segment.segment_id),
                short_number(segment.base), short_number(segment.limit), segment.permissions))
        count = len(table.segments)
        suffix = f" ({DISPLAY_LIMIT} hiện)" if count > DISPLAY_LIMIT else ""
        self.segment_count_var.set(f"{count:,} segment{suffix}")
        self.pause_play()
        self.playback.clear()
        self._map_table = table
        self.single_result = None
        self.trace_steps = ()
        self.trace_visible = 0
        self._show_trace()
        self._set_banner("Bảng segment đã sẵn sàng", "Nhập địa chỉ logic để bắt đầu phép dịch.")
        self._draw_map(table, None)
        self._set_status(f"{source} · {count:,} segment.")

    def load_sample(self) -> None:
        self.load_segments_path(PROJECT_ROOT / "input" / "segments.csv")

    def open_segments(self) -> None:
        path = filedialog.askopenfilename(parent=self.master, title="Mở bảng segment",
            initialdir=str(PROJECT_ROOT / "input"), filetypes=[("CSV", "*.csv"), ("Tất cả", "*.*")])
        if path:
            self.load_segments_path(path)

    def load_segments_path(self, path: str | Path) -> bool:
        """Parse and validate before mutating the visible table."""
        try:
            new_table = SegmentTable(load_segments(path))
        except (ValueError, OSError, UnicodeError) as exc:
            self._error(str(exc))
            return False
        self._replace_table(new_table, f"Đã mở {Path(path).name}")
        return True

    def _select_segment(self, event=None) -> None:
        selection = self.segment_tree.selection()
        if not selection:
            return
        segment = self.table.segments[int(selection[0])]
        self.segment_id_var.set(str(segment.segment_id))
        self.base_var.set(str(segment.base))
        self.limit_var.set(str(segment.limit))
        self.permissions_var.set(segment.permissions)
        self.address_segment_var.set(str(segment.segment_id))

    def upsert_segment(self) -> None:
        try:
            segment = Segment(int(self.segment_id_var.get()), int(self.base_var.get()),
                              int(self.limit_var.get()), self.permissions_var.get())
            candidates = list(self.table.segments)
            matching = next((i for i, existing in enumerate(candidates)
                             if existing.segment_id == segment.segment_id), None)
            if matching is None:
                candidates.append(segment)
            else:
                candidates[matching] = segment
            table = SegmentTable(candidates)
        except (ValueError, TypeError) as exc:
            self._error(f"Dữ liệu segment không hợp lệ: {exc}")
            return
        self._replace_table(table, f"Đã lưu segment {short_number(segment.segment_id)}")

    def remove_segment(self) -> None:
        selection = self.segment_tree.selection()
        if not selection:
            self._set_status("Chọn một dòng trong bảng segment để xóa.")
            return
        if len(self.table.segments) == 1:
            self._error("Bảng phải có ít nhất một segment. Hãy thêm segment khác trước khi xóa.")
            return
        index = int(selection[0])
        removed = self.table.segments[index]
        segments = [segment for i, segment in enumerate(self.table.segments) if i != index]
        self._replace_table(SegmentTable(segments), f"Đã xóa segment {short_number(removed.segment_id)}")

    def translate_single(self, step: bool = False) -> None:
        try:
            address = LogicalAddress(int(self.address_segment_var.get()), int(self.offset_var.get()),
                                     ACCESS_NAMES[self.access_var.get()])
            result = self.table.translate(address)
        except (ValueError, TypeError, KeyError) as exc:
            self._error(f"Địa chỉ nhập không hợp lệ: {exc}")
            return
        self.single_result = result
        self._present_result(result, self.table, step=step)
        if step:
            self._set_status("Đã nạp yêu cầu. Bấm Bước tiếp hoặc Tự chạy để bắt đầu kiểm tra.")
        else:
            self._set_status(f"Đã dịch ({short_number(result.segment_id)}, {short_number(result.offset)}) · {result.status}.")

    def _set_banner(self, title: str, detail: str, error: bool = False) -> None:
        background = COLORS["light_red"] if error else COLORS["light_teal"]
        foreground = COLORS["red"] if error else COLORS["teal"]
        self.result_box.configure(background=background)
        self.result_title.configure(text=title, background=background, foreground=foreground)
        self.result_detail.configure(text=detail, background=background)


    def _present_result(self, result: TranslationResult, table: SegmentTable, step: bool = False) -> None:
        self.pause_play()
        self.playback.load(result, complete=not step)
        self._map_table = table
        self._refresh_simulation()

    def _refresh_simulation(self) -> None:
        state, result = self.playback, self.playback.result
        self.pipeline_canvas.draw(state)
        self.map_canvas.draw(self._map_table, state)
        self._map_result = result
        self.trace_steps = tuple(s.description for s in result.steps) if result else ()
        self.trace_visible = state.visible
        lines = [f"{i + 1}. {s.title}: {s.description}" for i, s in
                 enumerate(result.steps[:state.visible])] if result else []
        self._write_text(self.trace_text, "\n".join(lines))
        self.trace_text.see("end")
        self.trace_label_var.set(f"Đã chạy {state.visible}/{state.total} bước")
        self.next_button.configure(state="normal" if result and not state.complete else "disabled")
        self.previous_button.configure(state="normal" if state.visible else "disabled")
        self.restart_button.configure(state="normal" if result else "disabled")
        if result is None:
            self._set_banner("Sẵn sàng mô phỏng", "Nhập địa chỉ hoặc nạp một tình huống mẫu.")
        elif not state.complete:
            detail = result.steps[state.visible - 1].description if state.visible else (
                f"Yêu cầu ({compact(result.segment_id)}, {compact(result.offset)}) · truy cập {result.access}."
                " Bấm Bước tiếp hoặc Tự chạy.")
            self._set_banner(f"Đang mô phỏng · {state.visible}/{state.total} bước", detail)
        elif result.status == "OK":
            self._set_banner(f"Địa chỉ vật lý: {compact(state.physical_address)}",
                f"{compact(result.base)} + {compact(result.offset)} = {compact(state.physical_address)}"
                f" · quyền {result.access} được phép.")
        else:
            self._set_banner(result.status, result.message, error=True)
        if result is not None:
            self._set_status(f"Hoàn tất · {result.status}." if state.complete else
                f"Đang mô phỏng ({compact(result.segment_id)}, {compact(result.offset)}) · "
                f"đã chạy {state.visible}/{state.total} bước.")

    @staticmethod
    def _write_text(widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _show_trace(self) -> None:
        self._refresh_simulation()

    def next_step(self) -> None:
        self.pause_play()
        self.playback.forward()
        self._refresh_simulation()

    def previous_step(self) -> None:
        self.pause_play()
        self.playback.backward()
        self._refresh_simulation()

    def restart_simulation(self) -> None:
        self.pause_play()
        self.playback.restart()
        self._refresh_simulation()

    def pause_play(self) -> None:
        if self._play_after is not None:
            self.after_cancel(self._play_after)
            self._play_after = None
        self.play_button.configure(text="▶ Tự chạy")

    def toggle_play(self) -> None:
        if self._play_after is not None:
            self.pause_play()
            return
        if self.playback.result is None:
            self.translate_single(step=True)
            if self.playback.result is None:
                return
        elif self.playback.complete:
            self.playback.restart()
            self._refresh_simulation()
        self.play_button.configure(text="Ⅱ Tạm dừng")
        self._play_after = self.after(self._play_delay(), self._auto_tick)

    def _play_delay(self) -> int:
        return {"0,5 giây": 500, "1 giây": 1000, "2 giây": 2000}.get(self.speed_var.get(), 1000)

    def _auto_tick(self) -> None:
        self._play_after = None
        self.playback.forward()
        self._refresh_simulation()
        if self.playback.complete:
            self.pause_play()
        else:
            self._play_after = self.after(self._play_delay(), self._auto_tick)

    def load_scenario(self) -> None:
        self.pause_play()
        segment_id, offset, access = self.scenarios[self.scenario_var.get()]
        if not self.load_segments_path(PROJECT_ROOT / "input" / "segments.csv"):
            return
        self.address_segment_var.set(str(segment_id))
        self.offset_var.set(str(offset))
        self.access_var.set(access)
        self.translate_single(step=True)
        self._set_status(f"Đã nạp tình huống: {self.scenario_var.get()}. Bấm Bước tiếp hoặc Tự chạy.")

    def _draw_map(self, table: SegmentTable, result: TranslationResult | None) -> None:
        self._map_table, self._map_result = table, result
        self.map_canvas.draw(table, self.playback)

    def _start_job(self, operation: Callable, callback: Callable, status: str) -> None:
        if self._job_running:
            self._set_status("Đang xử lý dữ liệu; vui lòng đợi tác vụ hiện tại hoàn tất.")
            return
        self._job_running = True
        self._job_callback = callback
        for button in (self.batch_run_button, self.batch_sample_button, self.export_button):
            button.configure(state="disabled")
        self.progress.start(12)
        self._set_status(status)

        def run() -> None:
            try:
                self._job_queue.put((True, operation()))
            except Exception as exc:  # Exceptions cross the thread boundary as data.
                self._job_queue.put((False, exc))

        threading.Thread(target=run, daemon=True, name="segmentation-csv-worker").start()
        self._job_after = self.after(50, self._poll_job)

    def _poll_job(self) -> None:
        self._job_after = None
        try:
            success, payload = self._job_queue.get_nowait()
        except queue.Empty:
            self._job_after = self.after(50, self._poll_job)
            return
        callback = self._job_callback
        self._job_running = False
        self._job_callback = None
        self.progress.stop()
        self.batch_run_button.configure(state="normal")
        self.batch_sample_button.configure(state="normal")
        self.export_button.configure(state="normal" if self.batch_results else "disabled")
        if success:
            callback(payload)
        else:
            self._error(f"Không thể xử lý CSV: {payload}")

    def open_addresses(self) -> None:
        path = filedialog.askopenfilename(parent=self.master, title="Mở danh sách địa chỉ logic",
            initialdir=str(PROJECT_ROOT / "input"), filetypes=[("CSV", "*.csv"), ("Tất cả", "*.*")])
        if path:
            self.run_batch_path(path)

    def run_batch_path(self, path: str | Path) -> None:
        snapshot = self.table
        def process():
            addresses = load_addresses(path)
            return (list(snapshot.translate_many(addresses)), snapshot, Path(path).name)
        self._start_job(process, self._accept_batch, "Đang đọc CSV và dịch địa chỉ…")

    def run_sample_batch(self) -> None:
        self.run_batch_path(PROJECT_ROOT / "input" / "addresses.csv")

    def _accept_batch(self, payload) -> None:
        results, table, source = payload
        self.batch_results, self.batch_table = results, table
        self.batch_tree.delete(*self.batch_tree.get_children())
        for index, result in enumerate(results[:DISPLAY_LIMIT]):
            self.batch_tree.insert("", "end", iid=str(index), values=(index + 1,
                short_number(result.segment_id), short_number(result.offset), result.access,
                STATUS_NAMES.get(result.status, result.status), short_number(result.physical_address)),
                tags=("ok" if result.status == "OK" else "error",))
        ok_count = sum(result.status == "OK" for result in results)
        self.batch_summary_var.set(f"{source}  ·  {len(results):,} địa chỉ  ·  {ok_count:,} hợp lệ"
            f"  ·  {len(results) - ok_count:,} bị từ chối  ·  bảng chụp: {len(table.segments):,} segment")
        self._write_text(self.batch_detail, "Chọn một dòng để xem thông tin và các bước xử lý.")
        self.export_button.configure(state="normal" if results else "disabled")
        self.batch_map_button.configure(state="disabled")
        self._set_status(f"Đã xử lý {len(results):,} địa chỉ. Có thể xuất toàn bộ kết quả CSV.")
        if results:
            self.batch_tree.selection_set("0")
            self._select_batch_result()

    def _select_batch_result(self, event=None) -> None:
        selection = self.batch_tree.selection()
        if not selection:
            return
        result = self.batch_results[int(selection[0])]
        lines = [f"Trạng thái: {result.status} · Segment {result.segment_id} · Offset {result.offset} · Thao tác {result.access}",
                 f"Địa chỉ vật lý: {result.physical_address if result.physical_address is not None else 'Không có'}", result.message]
        lines.extend(result.trace)
        self._write_text(self.batch_detail, "\n".join(lines))
        self.batch_map_button.configure(state="normal")

    def show_batch_map(self) -> None:
        selection = self.batch_tree.selection()
        if not selection:
            return
        result = self.batch_results[int(selection[0])]
        self._present_result(result, self.batch_table)
        self.notebook.select(self.simulator_tab)
        self._set_status("Đang xem kết quả CSV trên bảng segment đã chụp lúc chạy; bảng chỉnh sửa bên trái có thể khác.")

    def export_results(self) -> None:
        if not self.batch_results:
            self._set_status("Chạy danh sách địa chỉ trước khi xuất kết quả.")
            return
        path = filedialog.asksaveasfilename(parent=self.master, title="Xuất toàn bộ kết quả",
            initialdir=str(PROJECT_ROOT / "output"), initialfile="translation_results.csv",
            defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            results = self.batch_results
            self._start_job(lambda: save_results(path, results),
                lambda _: self._set_status(f"Đã xuất {len(results):,} kết quả tới {path}"), "Đang xuất kết quả CSV…")


def main() -> None:
    root = tk.Tk()
    SegmentationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
