"""Trạng thái phát mô phỏng và sơ đồ Canvas, dùng kết quả từ thuật toán.

Không dịch lại địa chỉ trong phần vẽ. Kết quả cuối chỉ được công bố khi
người xem đi tới bước tương ứng, kể cả khi lùi bước hoặc chạy lại.
"""
from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk

from .segmentation import SegmentTable, TranslationResult


STAGES = (
    ("lookup", "Tra segment"),
    ("bounds", "Kiểm tra giới hạn"),
    ("permission", "Kiểm tra r/w/x"),
    ("translation", "Base + offset"),
)
PALETTE = {
    "text": "#19334b", "muted": "#60778a", "line": "#d6e2eb",
    "pass": "#087e78", "pass_bg": "#dff3ed", "error": "#ba354c",
    "error_bg": "#fde9ed", "waiting": "#667b8b", "waiting_bg": "#edf2f6",
    "skipped": "#8a98a4", "skipped_bg": "#f4f6f8", "active": "#2865ab",
}


def compact(value: int | None, length: int = 18) -> str:
    if value is None:
        return "—"
    text = str(value)
    return text if len(text) <= length else f"{text[:7]}…{text[-5:]}"


@dataclass(frozen=True)
class StageView:
    stage: str
    title: str
    state: str


@dataclass
class Playback:
    result: TranslationResult | None = None
    visible: int = 0

    @property
    def total(self) -> int:
        return len(self.result.steps) if self.result else 0

    @property
    def complete(self) -> bool:
        return self.result is not None and self.visible >= self.total

    @property
    def physical_address(self) -> int | None:
        if self.complete and self.result.status == "OK":
            return self.result.physical_address
        return None

    def load(self, result: TranslationResult, *, complete: bool = False) -> None:
        self.result = result
        self.visible = len(result.steps) if complete else 0

    def forward(self) -> None:
        self.visible = min(self.total, self.visible + 1)

    def backward(self) -> None:
        self.visible = max(0, self.visible - 1)

    def restart(self) -> None:
        self.visible = 0

    def clear(self) -> None:
        self.result = None
        self.visible = 0

    def stages(self) -> tuple[StageView, ...]:
        revealed = {step.stage: step for step in self.result.steps[:self.visible]} if self.result else {}
        failed = any(not step.success for step in revealed.values())
        return tuple(StageView(key, title,
            ("pass" if revealed[key].success else "error") if key in revealed
            else ("skipped" if failed else "waiting")) for key, title in STAGES)


class PipelineCanvas(tk.Canvas):
    def __init__(self, master, **kwargs):
        super().__init__(master, background="white", highlightthickness=0, height=85, **kwargs)
        self.playback = Playback()
        self.bind("<Configure>", lambda _: self.draw(self.playback))

    def draw(self, playback: Playback) -> None:
        self.playback = playback
        self.delete("all")
        width = max(self.winfo_width(), 300)
        gap, margin = 17, 3
        cell = (width - margin * 2 - gap * 3) / 4
        labels = {"pass": "Đạt", "error": "Lỗi · dừng", "waiting": "Chưa chạy", "skipped": "Bỏ qua"}
        for index, stage in enumerate(playback.stages()):
            x = margin + index * (cell + gap)
            self.create_rectangle(x, 6, x + cell, 69, fill=PALETTE[stage.state + "_bg"],
                                  outline=PALETTE[stage.state], width=1, tags=(stage.stage, stage.state))
            self.create_text(x + cell / 2, 23, text=f"{index + 1:02d}  {stage.title}",
                             width=cell - 6, fill=PALETTE["text"], font=("Segoe UI", 9, "bold"))
            self.create_text(x + cell / 2, 52, text=labels[stage.state],
                             fill=PALETTE[stage.state], font=("Segoe UI", 9))
            if index < 3:
                self.create_line(x + cell + 3, 38, x + cell + gap - 3, 38,
                                 arrow="last", fill=PALETTE["muted"])


class MemoryCanvas(tk.Canvas):
    """Thang vật lý chung và thước offset riêng cho segment đang dịch."""
    def __init__(self, master, **kwargs):
        super().__init__(master, background="white", highlightthickness=0, height=220, **kwargs)
        self.table: SegmentTable | None = None
        self.playback = Playback()
        self.bind("<Configure>", lambda _: self.draw(self.table, self.playback))

    def draw(self, table: SegmentTable | None, playback: Playback) -> None:
        self.table, self.playback = table, playback
        self.delete("all")
        if table is None:
            return
        width, height = max(self.winfo_width(), 320), max(self.winfo_height(), 190)
        left, right = 76, width - 24
        span = right - left
        result = playback.result
        lookup_done = result is not None and playback.visible > 0
        selected = next((s for s in table.segments if lookup_done and s.segment_id == result.segment_id), None)
        failed = playback.complete and result.status != "OK" if result else False
        segments = list(table.segments[:6])
        if selected is not None and selected not in segments:
            segments[-1] = selected
        maximum = max(s.base + s.limit for s in table.segments)
        self.create_text(0, 8, text="BỘ NHỚ VẬT LÝ · thang địa chỉ chung", anchor="w",
                         fill=PALETTE["text"], font=("Segoe UI", 9, "bold"))
        self.create_line(left, 29, right, 29, fill=PALETTE["line"])
        self.create_text(left, 19, text="0", anchor="w", fill=PALETTE["muted"], font=("Segoe UI", 8))
        self.create_text(right, 19, text=compact(maximum - 1), anchor="e",
                         fill=PALETTE["muted"], font=("Segoe UI", 8))
        zoom_y = max(110, height - 100)
        row_h = min(25, max(8, (zoom_y - 56) / len(segments)))
        for index, segment in enumerate(segments):
            y = 38 + index * row_h
            active = segment is selected
            color = PALETTE["error"] if active and failed else PALETTE["pass"] if active else "#b6cbdc"
            x0 = min(right - 2, left + segment.base / maximum * span)
            x1 = max(x0 + 2, left + (segment.base + segment.limit) / maximum * span)
            self.create_text(1, y + 5, text=f"S{compact(segment.segment_id, 9)}", anchor="w",
                             fill=PALETTE["text"], font=("Segoe UI", 8, "bold"))
            self.create_rectangle(x0, y, x1, y + 10, fill=color, outline="", tags=("segment",))
            if active and playback.physical_address is not None:
                marker = left + playback.physical_address / maximum * span
                self.create_line(marker, y - 4, marker, y + 14, fill=PALETTE["text"], width=2,
                                 tags=("physical_marker",))
        if selected is None:
            text = "Bấm Từng bước để quan sát segment và offset."
            if lookup_done:
                text = f"Không có segment {compact(result.segment_id)} · không có địa chỉ vật lý."
            self.create_text(width / 2, zoom_y + 30, text=text, width=width - 20,
                             fill=PALETTE["muted"], font=("Segoe UI", 10))
        else:
            self.create_text(0, zoom_y, anchor="w", text=f"PHÓNG TO S{compact(selected.segment_id)}"
                f"  ·  base {compact(selected.base)}  ·  quyền {selected.permissions}",
                fill=PALETTE["text"], font=("Segoe UI", 9, "bold"))
            bar_y = zoom_y + 24
            self.create_rectangle(left, bar_y, right, bar_y + 16,
                                  fill="#dff3ed", outline=PALETTE["pass"], tags=("offset_range",))
            self.create_text(left, bar_y + 28, text="offset 0", anchor="w",
                             fill=PALETTE["muted"], font=("Segoe UI", 8))
            self.create_text(right, bar_y + 28, text=f"limit {compact(selected.limit)} (loại trừ)",
                             anchor="e", fill=PALETTE["muted"], font=("Segoe UI", 8))
            bounds_done = any(step.stage == "bounds" for step in result.steps[:playback.visible])
            if bounds_done:
                # Clamp only the drawing; the exact out-of-range offset remains in the label.
                ratio = 0.0 if result.offset < 0 else 1.0 if result.offset >= selected.limit else result.offset / selected.limit
                marker = left + ratio * span
                if result.offset < 0:
                    marker -= 10
                elif result.offset >= selected.limit:
                    marker += 10
                color = PALETTE["error"] if failed else PALETTE["active"]
                self.create_line(marker, bar_y - 5, marker, bar_y + 21,
                                 fill=color, width=3, tags=("offset_marker",))
                self.create_polygon(marker - 4, bar_y - 7, marker + 4, bar_y - 7,
                                    marker, bar_y - 1, fill=color, outline="")
                self.create_text(left, bar_y + 48, anchor="w", text=f"offset yêu cầu = {compact(result.offset)}"
                    + (" · ngoài đoạn" if not 0 <= result.offset < selected.limit else ""),
                    fill=color, font=("Segoe UI", 9))
        self.create_text(right, 8, anchor="e", text=f"{len(segments)}/{len(table.segments)} segment",
                         fill=PALETTE["muted"], font=("Segoe UI", 8))
