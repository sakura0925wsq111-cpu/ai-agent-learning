"""Conservative geometric grouping of OCR source lines before filtering.

This preserves local text runs, not inferred semantic paragraphs. It never uses
recognition confidence or acceptance decisions to drop a line while grouping.
"""

from __future__ import annotations

import re


_ITEM_START = re.compile(
    r"^\s*(?:[•●▪■*-]\s+|\d+[.)、]\s*(?!\d)|[（(]\d+[）)]|[一二三四五六七八九十]+、)"
)
_SENTENCE_END = re.compile(r"(?:[。！？!?；;]|(?<!\d)\.)[\"'）)\]】」』]*$")


def _union_box(boxes: list[list[float]]) -> list[float]:
    return [
        min(box[0] for box in boxes), min(box[1] for box in boxes),
        max(box[2] for box in boxes), max(box[3] for box in boxes),
    ]


def group_source_paragraphs(
    records: list[dict], image_size: tuple[int, int]
) -> list[list[int]]:
    """Return source indices grouped by row, column, spacing and item boundaries.

    Thresholds are relative to line height, rather than a particular PDF/DPI.
    Nearby fragments on the same baseline belong to one row. Vertically close,
    aligned rows belong to one paragraph; large gaps, different columns, large
    font changes, completed sentences and new list items end that paragraph.
    Rejected/formula/noise rows participate just like other source rows.
    """
    if not records:
        return []
    width, height = image_size
    if width <= 0 or height <= 0:
        raise ValueError("image dimensions must be positive")
    boxes = [
        [box[0] * width, box[1] * height, box[2] * width, box[3] * height]
        for box in (record["bbox"] for record in records)
    ]
    parent = list(range(len(records)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def join(first: int, second: int) -> None:
        parent[find(second)] = find(first)

    # OCR may split an inline formula or a colour change into separate boxes.
    for first, a in enumerate(boxes):
        for second in range(first + 1, len(boxes)):
            b = boxes[second]
            a_height, b_height = a[3] - a[1], b[3] - b[1]
            if min(a_height, b_height) <= 0:
                continue
            overlap = min(a[3], b[3]) - max(a[1], b[1])
            gap = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
            if (
                overlap / min(a_height, b_height) >= 0.55
                and min(a_height, b_height) / max(a_height, b_height) >= 0.35
                and gap <= 0.9 * max(a_height, b_height)
            ):
                join(first, second)

    row_members: dict[int, list[int]] = {}
    for index in range(len(records)):
        row_members.setdefault(find(index), []).append(index)
    rows = [
        sorted(indices, key=lambda index: (boxes[index][0], boxes[index][1]))
        for indices in row_members.values()
    ]
    rows.sort(key=lambda indices: (
        min(boxes[index][1] for index in indices),
        min(boxes[index][0] for index in indices),
    ))
    row_boxes = [_union_box([boxes[index] for index in row]) for row in rows]

    for upper_index, a in enumerate(row_boxes):
        a_height = a[3] - a[1]
        candidates = []
        for lower_index in range(upper_index + 1, len(rows)):
            b = row_boxes[lower_index]
            b_height = b[3] - b[1]
            if min(a_height, b_height, a[2] - a[0], b[2] - b[0]) <= 0:
                continue
            gap = b[1] - a[3]
            horizontal_overlap = min(a[2], b[2]) - max(a[0], b[0])
            if (
                b[1] >= a[1] + 0.4 * min(a_height, b_height)
                and -0.35 * min(a_height, b_height) <= gap
                and gap <= 0.7 * max(a_height, b_height)
                and horizontal_overlap / min(a[2] - a[0], b[2] - b[0]) >= 0.6
                and abs(a[0] - b[0]) <= 1.5 * max(a_height, b_height)
            ):
                candidates.append(lower_index)
        if not candidates:
            continue
        # Never jump over an intervening source row to join only the good rows.
        lower_index = min(candidates, key=lambda index: row_boxes[index][1])
        b = row_boxes[lower_index]
        b_height = b[3] - b[1]
        upper_text = " ".join(records[index]["text"] for index in rows[upper_index])
        lower_text = " ".join(records[index]["text"] for index in rows[lower_index])
        if (
            min(a_height, b_height) / max(a_height, b_height) < 0.65
            or _SENTENCE_END.search(upper_text.rstrip())
            or _ITEM_START.search(lower_text)
        ):
            continue
        join(rows[upper_index][0], rows[lower_index][0])

    paragraphs: dict[int, list[int]] = {}
    for row in rows:
        paragraphs.setdefault(find(row[0]), []).extend(row)
    return sorted(paragraphs.values(), key=lambda indices: (
        min(boxes[index][1] for index in indices),
        min(boxes[index][0] for index in indices),
    ))


__all__ = ["group_source_paragraphs"]
