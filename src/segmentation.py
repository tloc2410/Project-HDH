"""Lõi dịch địa chỉ phân đoạn, độc lập với giao diện và định dạng tệp.

Mô hình một tiến trình dùng segment có độ dài ``limit``. Khoảng vật lý là
``[base, base + limit)``; các segment không chồng lấn. Địa chỉ là số nguyên
Python không âm và không bị ép vào kích thước thanh ghi phần cứng cụ thể.
"""

from dataclasses import dataclass
from typing import Iterable, Optional


def _require_integer(value: object, label: str) -> None:
    if type(value) is not int:
        raise ValueError(f"{label} phải là số nguyên.")


@dataclass(frozen=True)
class Segment:
    segment_id: int
    base: int
    limit: int
    permissions: str = "rw"

    def __post_init__(self) -> None:
        for value, label in (
            (self.segment_id, "Mã segment"),
            (self.base, "Base"),
            (self.limit, "Limit"),
        ):
            _require_integer(value, label)
        if self.segment_id < 0:
            raise ValueError("Mã segment phải không âm.")
        if self.base < 0:
            raise ValueError("Base phải không âm.")
        if self.limit <= 0:
            raise ValueError("Limit phải lớn hơn 0 (độ dài segment).")
        if (
            not isinstance(self.permissions, str)
            or not self.permissions
            or set(self.permissions) - set("rwx")
            or len(set(self.permissions)) != len(self.permissions)
        ):
            raise ValueError("Quyền phải gồm các ký tự r, w, x không lặp, ví dụ r hoặc rw.")


@dataclass(frozen=True)
class LogicalAddress:
    segment_id: int
    offset: int
    access: str = "r"

    def __post_init__(self) -> None:
        _require_integer(self.segment_id, "Mã segment")
        _require_integer(self.offset, "Offset")
        if self.segment_id < 0:
            raise ValueError("Mã segment phải không âm.")
        if not isinstance(self.access, str) or self.access not in ("r", "w", "x"):
            raise ValueError("Thao tác truy cập phải là r (đọc), w (ghi) hoặc x (thực thi).")


@dataclass(frozen=True)
class TranslationStep:
    """Một giai đoạn đã chạy, dùng trực tiếp để trực quan hóa.

    ``stage`` là một trong lookup, bounds, permission, translation. Khi một
    bước thất bại, các bước tiếp theo không tồn tại trong kết quả. Giao diện
    không cần suy luận trạng thái từ chuỗi mô tả hoặc tính lại thuật toán.
    """

    stage: str
    title: str
    description: str
    success: bool


@dataclass(frozen=True)
class TranslationResult:
    segment_id: int
    offset: int
    access: str
    base: Optional[int]
    limit: Optional[int]
    status: str
    physical_address: Optional[int]
    message: str
    trace: tuple[str, ...]
    steps: tuple[TranslationStep, ...] = ()


class SegmentTable:
    """Bảng bất biến với chỉ mục tra cứu theo mã segment, trung bình O(1)."""

    def __init__(self, segments: Iterable[Segment]) -> None:
        entries = tuple(segments)
        if not entries:
            raise ValueError("Bảng segment phải có ít nhất một segment.")
        index: dict[int, Segment] = {}
        for segment in entries:
            if not isinstance(segment, Segment):
                raise ValueError("Mỗi phần tử trong bảng phải là một Segment.")
            if segment.segment_id in index:
                raise ValueError(f"Mã segment {segment.segment_id} bị trùng.")
            index[segment.segment_id] = segment
        ordered = sorted(entries, key=lambda segment: segment.base)
        for previous, current in zip(ordered, ordered[1:]):
            if current.base < previous.base + previous.limit:
                raise ValueError(
                    f"Segment {previous.segment_id} và {current.segment_id} chồng lấn "
                    "vùng nhớ vật lý; mô hình này không cho phép chồng lấn."
                )
        self._segments = entries
        self._index = index

    @property
    def segments(self) -> tuple[Segment, ...]:
        return self._segments

    def translate(self, address: LogicalAddress) -> TranslationResult:
        if not isinstance(address, LogicalAddress):
            raise ValueError("Địa chỉ phải là một LogicalAddress.")
        trace = [f"1. Tra bảng segment với mã {address.segment_id}."]
        steps: list[TranslationStep] = []
        segment = self._index.get(address.segment_id)

        def result(status: str, physical: Optional[int], message: str) -> TranslationResult:
            return TranslationResult(
                segment_id=address.segment_id,
                offset=address.offset,
                access=address.access,
                base=segment.base if segment is not None else None,
                limit=segment.limit if segment is not None else None,
                status=status,
                physical_address=physical,
                message=message,
                trace=tuple(trace),
                steps=tuple(steps),
            )

        if segment is None:
            message = f"Không tìm thấy segment {address.segment_id}."
            trace.append(f"2. {message} Dừng dịch địa chỉ.")
            steps.append(TranslationStep("lookup", "Tra bảng segment", message, False))
            return result("SEGMENT_NOT_FOUND", None, message)

        trace.append(
            f"2. Đọc base = {segment.base}, limit = {segment.limit}, "
            f"quyền = {segment.permissions}."
        )
        steps.append(TranslationStep(
            "lookup", "Tra bảng segment",
            f"Segment {segment.segment_id}: base = {segment.base}, "
            f"limit = {segment.limit}, quyền = {segment.permissions}.", True,
        ))
        if not 0 <= address.offset < segment.limit:
            message = (
                f"Segmentation fault: offset {address.offset} nằm ngoài "
                f"[0, {segment.limit - 1}]."
            )
            trace.append(f"3. Kiểm tra 0 <= {address.offset} < {segment.limit}: sai. {message}")
            steps.append(TranslationStep("bounds", "Kiểm tra giới hạn", message, False))
            return result("SEGMENTATION_FAULT", None, message)

        trace.append(f"3. Kiểm tra 0 <= {address.offset} < {segment.limit}: hợp lệ.")
        steps.append(TranslationStep(
            "bounds", "Kiểm tra giới hạn",
            f"0 ≤ {address.offset} < {segment.limit}: hợp lệ.", True,
        ))
        if address.access not in segment.permissions:
            message = (
                f"Protection fault: segment {segment.segment_id} có quyền "
                f"{segment.permissions}, không cho phép thao tác {address.access}."
            )
            trace.append(f"4. {message} Dừng dịch địa chỉ.")
            steps.append(TranslationStep("permission", "Kiểm tra quyền", message, False))
            return result("PROTECTION_FAULT", None, message)

        trace.append(f"4. Kiểm tra quyền {address.access}: được phép.")
        steps.append(TranslationStep(
            "permission", "Kiểm tra quyền",
            f"Quyền {address.access} được phép trong {segment.permissions}.", True,
        ))
        physical_address = segment.base + address.offset
        trace.append(f"5. Địa chỉ vật lý = {segment.base} + {address.offset} = {physical_address}.")
        steps.append(TranslationStep(
            "translation", "Tính địa chỉ vật lý",
            f"{segment.base} + {address.offset} = {physical_address}.", True,
        ))
        return result("OK", physical_address, "Dịch địa chỉ thành công.")

    def translate_many(self, addresses: Iterable[LogicalAddress]) -> list[TranslationResult]:
        return [self.translate(address) for address in addresses]
