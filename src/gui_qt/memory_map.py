"""Sơ đồ vùng nhớ vật lý cho giao diện PySide6."""

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..segmentation import SegmentTable, TranslationResult


TEXT = QColor("#142b50")
MUTED = QColor("#5373a3")
TRACK = QColor("#e5edf8")
SEGMENT = QColor("#a9c8f2")
ACTIVE = QColor("#2b73f4")
ERROR = QColor("#bb3543")
DISPLAY_LIMIT = 6


def _compact(value: int) -> str:
    text = str(value)
    return text if len(text) <= 12 else f"{text[:5]}…{text[-4:]}"


def _text(painter: QPainter, rect: QRect, text: str, color: QColor = TEXT, *, right: bool = False) -> None:
    alignment = Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft
    clipped = painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, rect.width())
    painter.setPen(color)
    painter.drawText(rect, (alignment | Qt.AlignmentFlag.AlignVCenter).value, clipped)


def _marker(painter: QPainter, x: int, y: int, color: QColor) -> None:
    painter.setPen(QPen(color, 2))
    painter.drawLine(x, y - 3, x, y + 13)


class MemoryMapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 196)
        self.setAccessibleName("Sơ đồ vùng nhớ vật lý")
        self.table: SegmentTable | None = None
        self.result: TranslationResult | None = None
        self.visible_steps = 0

    def set_state(
        self,
        table: SegmentTable | None,
        result: TranslationResult | None = None,
        visible_steps: int = 0,
    ) -> None:
        self.table = table
        self.result = result
        self.visible_steps = visible_steps
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        try:
            self._draw(painter)
        finally:
            painter.end()

    def _draw(self, painter: QPainter) -> None:
        width = self.width()
        if self.table is None:
            _text(painter, QRect(0, 0, width, 24), "Chưa có bảng phân đoạn.", MUTED)
            return

        result = self.result
        revealed = result.steps[:self.visible_steps] if result else ()
        lookup_done = any(step.stage == "lookup" and step.success for step in revealed)
        physical = None
        if result is not None and result.status == "OK" and len(revealed) == len(result.steps):
            physical = result.physical_address
        selected = next(
            (segment for segment in self.table.segments if segment.segment_id == result.segment_id),
            None,
        ) if lookup_done else None
        failed = any(not step.success for step in revealed)
        highlight = ERROR if failed else ACTIVE

        shown = list(self.table.segments[:DISPLAY_LIMIT])
        if selected is not None and selected not in shown:
            shown[-1] = selected
        end = max(segment.base + segment.limit for segment in self.table.segments)
        label_width = min(136, width // 3)
        left = 52
        right = width - label_width - 8
        span = right - left

        _text(painter, QRect(0, 0, width // 2, 19), "Thang địa chỉ vật lý")
        _text(painter, QRect(width // 2, 0, width // 2, 19),
              f"{len(shown)}/{len(self.table.segments)} phân đoạn", MUTED, right=True)
        _text(painter, QRect(left, 19, span, 15), "0", MUTED)
        _text(painter, QRect(left, 19, span, 15), _compact(end - 1), MUTED, right=True)

        for index, segment in enumerate(shown):
            y = 35 + index * 17
            active = segment is selected
            color = highlight if active else SEGMENT
            start = left + segment.base * span // end
            stop = left + (segment.base + segment.limit) * span // end
            painter.fillRect(QRect(left, y + 3, span, 10), TRACK)
            painter.fillRect(QRect(start, y + 3, max(1, stop - start), 10), color)
            _text(painter, QRect(0, y, left - 4, 16), f"S{_compact(segment.segment_id)}")
            _text(painter, QRect(right + 8, y, label_width, 16),
                  f"{_compact(segment.base)} – {_compact(segment.base + segment.limit - 1)}", MUTED)
            if active and physical is not None:
                _marker(painter, left + physical * span // end, y + 3, TEXT)

        detail_y = 39 + len(shown) * 17
        if selected is None:
            message = f"Không tìm thấy segment {_compact(result.segment_id)}." if revealed else (
                "Dịch địa chỉ để xem vị trí offset trên sơ đồ."
            )
            _text(painter, QRect(0, detail_y, width, 24), message, ERROR if revealed else MUTED)
            return

        summary = (f"S{_compact(selected.segment_id)} · Base {_compact(selected.base)}"
                   f" · Limit {_compact(selected.limit)} · Quyền {selected.permissions}")
        _text(painter, QRect(0, detail_y, width, 18), summary)
        bar_y = detail_y + 20
        inset = 8
        bar_width = width - 2 * inset
        painter.fillRect(QRect(inset, bar_y, bar_width, 10), TRACK)
        bounds = next((step for step in revealed if step.stage == "bounds"), None)
        if bounds is not None:
            offset = result.offset
            if bounds.success:
                offset_position = offset * bar_width // selected.limit
            else:
                offset_position = -4 if offset < 0 else bar_width + 4
            _marker(painter, inset + offset_position, bar_y, highlight)
            label = f"Offset {_compact(offset)}"
            if not bounds.success:
                label += " · ngoài phân đoạn"
            elif physical is not None:
                label += f" → Địa chỉ vật lý {_compact(physical)}"
            _text(painter, QRect(inset, bar_y + 13, bar_width, 17), label, highlight)
