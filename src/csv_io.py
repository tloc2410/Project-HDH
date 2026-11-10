"""Đọc CSV có kiểm tra cấu trúc và xuất kết quả UTF-8 BOM cho Excel."""

import csv
from pathlib import Path
import re
from typing import Iterable, Union

from .segmentation import LogicalAddress, Segment, SegmentTable, TranslationResult

PathLike = Union[str, Path]
RESULT_FIELDS = (
    "segment_id", "offset", "access", "base", "limit", "status",
    "physical_address", "message", "trace",
)


def _load_rows(path: PathLike, required: set[str], optional: set[str]) -> list[tuple[int, dict[str, str]]]:
    rows: list[tuple[int, dict[str, str]]] = []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source, strict=True)
            headers = reader.fieldnames
            if not headers:
                raise ValueError("Tệp CSV rỗng hoặc thiếu dòng tiêu đề.")
            if len(set(headers)) != len(headers):
                raise ValueError("CSV có tên cột bị trùng.")
            missing = required - set(headers)
            unknown = set(headers) - required - optional
            if missing:
                raise ValueError(f"CSV thiếu cột bắt buộc: {', '.join(sorted(missing))}.")
            if unknown:
                raise ValueError(f"CSV có cột không được hỗ trợ: {', '.join(sorted(unknown))}.")
            for row in reader:
                line = reader.line_num
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"Dòng {line}: số ô dữ liệu không khớp số cột tiêu đề.")
                clean = {key: value.strip() for key, value in row.items()}
                if any(not value for value in clean.values()):
                    raise ValueError(f"Dòng {line}: có ô dữ liệu trống.")
                rows.append((line, clean))
    except UnicodeDecodeError as exc:
        raise ValueError("CSV phải được lưu bằng UTF-8 hoặc UTF-8 BOM.") from exc
    except csv.Error as exc:
        raise ValueError(f"CSV không đúng định dạng: {exc}.") from exc
    if not rows:
        raise ValueError("CSV có tiêu đề nhưng chưa có dòng dữ liệu.")
    return rows


def _integer(value: str, name: str) -> int:
    if re.fullmatch(r"[+-]?[0-9]+", value) is None:
        raise ValueError(f"Cột {name} phải là số nguyên thập phân, nhận được {value!r}.")
    return int(value)


def load_segments(path: PathLike) -> list[Segment]:
    segments: list[Segment] = []
    for line, row in _load_rows(path, {"segment_id", "base", "limit"}, {"permissions"}):
        try:
            segments.append(Segment(
                segment_id=_integer(row["segment_id"], "segment_id"),
                base=_integer(row["base"], "base"),
                limit=_integer(row["limit"], "limit"),
                permissions=row.get("permissions", "rw"),
            ))
        except ValueError as exc:
            raise ValueError(f"Dòng {line}: {exc}") from exc
    SegmentTable(segments)  # Kiểm tra trùng mã và chồng lấn trước khi đưa lên giao diện.
    return segments


def load_addresses(path: PathLike) -> list[LogicalAddress]:
    addresses: list[LogicalAddress] = []
    for line, row in _load_rows(path, {"segment_id", "offset"}, {"access"}):
        try:
            addresses.append(LogicalAddress(
                segment_id=_integer(row["segment_id"], "segment_id"),
                offset=_integer(row["offset"], "offset"),
                access=row.get("access", "r"),
            ))
        except ValueError as exc:
            raise ValueError(f"Dòng {line}: {exc}") from exc
    return addresses


def save_results(path: PathLike, results: Iterable[TranslationResult]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        for result in results:
            writer.writerow({
                "segment_id": result.segment_id,
                "offset": result.offset,
                "access": result.access,
                "base": result.base,
                "limit": result.limit,
                "status": result.status,
                "physical_address": result.physical_address,
                "message": result.message,
                "trace": "\n".join(result.trace),
            })
