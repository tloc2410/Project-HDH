"""Kết nối giao diện Qt với bộ mô phỏng và xử lý CSV của dự án."""

from datetime import datetime
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from PySide6.QtWidgets import QFileDialog, QMessageBox

from ..csv_io import load_addresses, load_segments, save_results
from ..segmentation import LogicalAddress, Segment, SegmentTable, TranslationResult
from .memory_map import MemoryMapWidget


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_SEGMENTS = PROJECT_ROOT / "input" / "segments.csv"


def _decimal(value: str, label: str) -> int:
    if re.fullmatch(r"[+-]?[0-9]+", value) is None:
        raise ValueError(f"{label} phải là số nguyên thập phân.")
    return int(value)


def _segment_from_form(data: dict) -> Segment:
    return Segment(
        segment_id=_decimal(data["id"], "Mã segment"),
        base=_decimal(data["base"], "Base"),
        limit=_decimal(data["limit"], "Limit"),
        permissions=data["permission"].replace("-", ""),
    )


def _result_text(result: TranslationResult) -> str:
    if result.status == "OK":
        return f"OK · Địa chỉ vật lý {result.physical_address}"
    return f"{result.status} · {result.message}"


class SimulatorController:
    def __init__(self, window):
        self.window = window
        self.dashboard = window.dashboard
        self.csv_page = window.csv_page
        self._sample_table = SegmentTable(load_segments(SAMPLE_SEGMENTS))
        self.history: list[dict] = []
        self.batch_results: list[TranslationResult] = []
        self.memory_map = MemoryMapWidget()
        self.dashboard.set_memory_widget(self.memory_map)

        self.dashboard.add_requested.connect(self.add_segment)
        self.dashboard.edit_requested.connect(self.edit_segment)
        self.dashboard.delete_requested.connect(self.delete_segment)
        self.dashboard.translate_requested.connect(self.translate)
        self.dashboard.step_requested.connect(lambda data: self.translate(data, step=True))
        self.dashboard.next_step_requested.connect(self.next_step)
        self.dashboard.history_requested.connect(lambda: window.show_page(1))
        self.window.reset_requested.connect(self.reset)
        self.csv_page.load_segments_requested.connect(self._open_segments)
        self.csv_page.translate_csv_requested.connect(self._open_addresses)
        self.csv_page.export_requested.connect(self._save_results)

        self.reset()

    def reset(self) -> None:
        self.history.clear()
        self.batch_results.clear()
        self.dashboard.segment_input.clear()
        self.dashboard.offset_input.clear()
        self.dashboard.operation.setCurrentIndex(0)
        self._replace_table(self._sample_table)
        self._refresh_history()
        self.csv_page.set_export_enabled(False)
        self.csv_page.set_status("Đã nạp bảng phân đoạn mẫu. Chọn tệp CSV để bắt đầu.")
        self.window.show_page(0)

    def _error(self, error: Exception) -> None:
        QMessageBox.warning(self.window, "Không thể thực hiện", str(error))

    def _replace_table(self, table: SegmentTable) -> None:
        self.table = table
        self._result = None
        self._visible_steps = 0
        self.dashboard.set_segments(
            {
                "id": segment.segment_id,
                "base": segment.base,
                "limit": segment.limit,
                "permission": "".join(p if p in segment.permissions else "-" for p in "rwx"),
            }
            for segment in table.segments
        )
        self.dashboard.show_result("Bảng phân đoạn đã sẵn sàng. Nhập địa chỉ logic để bắt đầu.")
        self.dashboard.set_next_step_enabled(False)
        self.memory_map.set_state(table)

    def add_segment(self, data: dict) -> bool:
        try:
            segment = _segment_from_form(data)
            table = SegmentTable((*self.table.segments, segment))
        except ValueError as exc:
            self._error(exc)
            return False
        self._replace_table(table)
        return True

    def edit_segment(self, data: dict) -> bool:
        try:
            segment = _segment_from_form(data)
            if not any(current.segment_id == segment.segment_id for current in self.table.segments):
                raise ValueError(f"Không tìm thấy segment {segment.segment_id}.")
            table = SegmentTable(
                segment if current.segment_id == segment.segment_id else current
                for current in self.table.segments
            )
        except ValueError as exc:
            self._error(exc)
            return False
        self._replace_table(table)
        return True

    def delete_segment(self, segment_id: int) -> bool:
        try:
            remaining = [segment for segment in self.table.segments if segment.segment_id != segment_id]
            if len(remaining) == len(self.table.segments):
                raise ValueError(f"Không tìm thấy segment {segment_id}.")
            table = SegmentTable(remaining)
        except ValueError as exc:
            self._error(exc)
            return False
        self._replace_table(table)
        return True

    def translate(self, data: dict, *, step: bool = False) -> bool:
        try:
            address = LogicalAddress(
                segment_id=_decimal(data["segment_id"], "Mã segment"),
                offset=_decimal(data["offset"], "Offset"),
                access=data["operation"],
            )
        except ValueError as exc:
            self._error(exc)
            return False
        self._result = self.table.translate(address)
        self._visible_steps = 0 if step else len(self._result.steps)
        self._show_translation(self._result)
        if not step:
            self._record_results([self._result])
        return True

    def next_step(self) -> None:
        result = self._result
        if result is None or self._visible_steps >= len(result.steps):
            return
        self._visible_steps += 1
        self._show_translation(result)
        if self._visible_steps == len(result.steps):
            self._record_results([result])

    def _show_translation(self, result: TranslationResult) -> None:
        steps = result.steps[:self._visible_steps]
        complete = self._visible_steps == len(result.steps)
        details = "\n".join(
            f"{index}. {step.title} — {step.description}"
            for index, step in enumerate(steps, start=1)
        )
        if complete:
            self.dashboard.show_result(_result_text(result), result.status == "OK", details)
        else:
            self.dashboard.show_result(
                f"Đã xem {self._visible_steps}/4 bước. Bấm Bước tiếp để tiếp tục.",
                details=details,
            )
        self.dashboard.set_next_step_enabled(not complete)
        self.memory_map.set_state(self.table, result, self._visible_steps)

    def _refresh_history(self) -> None:
        self.dashboard.set_history(self.history[:5])
        self.window.set_history(self.history)

    def _record_results(self, results: list[TranslationResult]) -> None:
        time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        records = [
            {
                "time": time,
                "segment": result.segment_id,
                "offset": result.offset,
                "operation": result.access,
                "result": _result_text(result),
            }
            for result in results
        ]
        self.history[:0] = records
        self._refresh_history()

    def load_segments_path(self, path: str | Path) -> bool:
        try:
            table = SegmentTable(load_segments(path))
        except (OSError, ValueError) as exc:
            self._error(exc)
            return False
        self._replace_table(table)
        self.csv_page.set_status(f"Đã nạp {len(table.segments)} phân đoạn từ {Path(path).name}.")
        return True

    def translate_csv_path(self, path: str | Path) -> bool:
        try:
            results = self.table.translate_many(load_addresses(path))
        except (OSError, ValueError) as exc:
            self._error(exc)
            return False
        self.batch_results = results
        self._record_results(results)
        success_count = sum(result.status == "OK" for result in results)
        self.csv_page.set_status(
            f"Đã dịch {len(results)} địa chỉ từ {Path(path).name}. "
            f"{success_count} địa chỉ hợp lệ, {len(results) - success_count} lỗi mô phỏng."
        )
        self.csv_page.set_export_enabled(True)
        return True

    def export_results_path(self, path: str | Path) -> bool:
        if not self.batch_results:
            self._error(ValueError("Hãy dịch một tệp địa chỉ CSV trước khi xuất kết quả."))
            return False
        target = Path(path)
        try:
            with TemporaryDirectory(dir=target.parent) as folder:
                staged = Path(folder) / "results.csv"
                save_results(staged, self.batch_results)
                staged.replace(target)
        except (OSError, ValueError) as exc:
            self._error(exc)
            return False
        self.csv_page.set_status(f"Đã xuất {len(self.batch_results)} kết quả vào {target.name}.")
        return True

    def _open_segments(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Chọn bảng phân đoạn", str(PROJECT_ROOT / "input"), "Tệp CSV (*.csv)"
        )
        if path:
            self.load_segments_path(path)

    def _open_addresses(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Chọn tệp địa chỉ logic", str(PROJECT_ROOT / "input"), "Tệp CSV (*.csv)"
        )
        if path:
            self.translate_csv_path(path)

    def _save_results(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self.window, "Xuất kết quả dịch", str(PROJECT_ROOT / "output" / "results_qt.csv"), "Tệp CSV (*.csv)"
        )
        if path:
            self.export_results_path(path)
