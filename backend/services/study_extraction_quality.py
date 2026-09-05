"""Deterministic safety gate for raw OCR page results."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from statistics import fmean

from services.study_ocr import OCRBlock
from services.study_paragraphs import group_source_paragraphs


PARAGRAPH_GATE_VERSION = "paragraph-v1"


_FORMULA_SYMBOLS = set("=±×÷√∑∫∏≈≠≤≥∞∂∇σΣτγφΦΔδλμρΩω")
_DEPENDENCY_RE = re.compile(
    r"公式|下式|代入|计算步骤|其中|如图|见图|由式|可得|求解|计算如下"
)
_DATE_RE = re.compile(r"^\d{4}[-./年]\d{1,2}(?:[-./月]\d{1,2}日?)?$")
_PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")
_SECTION_NUMBER_RE = re.compile(r"^\d+(?:\.\d+){1,3}$")
_SHORT_LATIN_RE = re.compile(r"^[A-Za-z0-9_.()\[\]+\-*/\\]+$")
_LOGO_RE = re.compile(r"^[0-9]*[A-Z]{2,8}[0-9]*$")
_CONTEXT_FRAGMENT_RE = re.compile(
    r"^(表现出|说明了?|表明了?|因此|所以|从而|可见|由此|其中|该|其)"
)
_PUNCTUATION_FOR_COMPARISON = str.maketrans("，。；：！？、", ",.;:!? ")


@dataclass(frozen=True)
class ExtractionAssessment:
    raw_text: str
    safe_text: str
    quality_status: str
    quality_reasons: list[str]
    confidence: float | None
    blocks: list[dict]


def _comparison_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).translate(_PUNCTUATION_FOR_COMPARISON)
    value = re.sub(r"\s+", "", value)
    return value.rstrip(",.;:!?")


def _unbalanced_delimiters(text: str) -> bool:
    normalized = unicodedata.normalize("NFKC", text)
    return any(
        normalized.count(left) != normalized.count(right)
        for left, right in (("(", ")"), ("[", "]"), ("{", "}"), ("<", ">"))
    )


def _formula_like(text: str) -> bool:
    compact = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))
    if _DATE_RE.fullmatch(compact) or _SECTION_NUMBER_RE.fullmatch(compact):
        return False
    if any(char in _FORMULA_SYMBOLS for char in compact):
        return True
    if re.search(r"[A-Za-z]\w*\([^)]*[+\-*/][^)]*\)", compact):
        return True
    operators = sum(char in "+-*/^_" for char in compact)
    return operators >= 2 and bool(re.search(r"[A-Za-z0-9]", compact))


def _noise_like(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if len(compact) <= 1:
        return True
    if (
        _PAGE_NUMBER_RE.fullmatch(compact)
        or _SECTION_NUMBER_RE.fullmatch(compact)
        or _DATE_RE.fullmatch(compact)
    ):
        return True
    if _LOGO_RE.fullmatch(compact):
        return True
    control_or_replacement = sum(
        unicodedata.category(char).startswith("C") or char == "�" for char in compact
    )
    return control_or_replacement / max(len(compact), 1) > 0.05


def _relative_bbox(block: OCRBlock, image_size: tuple[int, int]) -> list[float]:
    width, height = image_size
    x1, y1, x2, y2 = block.bbox
    return [
        round(x1 / width, 6),
        round(y1 / height, 6),
        round(x2 / width, 6),
        round(y2 / height, 6),
    ]


def _iou(first: list[float], second: list[float]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    if intersection == 0:
        return 0.0
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    return intersection / max(first_area + second_area - intersection, 1e-9)


def _match_blocks(
    primary: list[OCRBlock],
    verification: list[OCRBlock],
    primary_size: tuple[int, int],
    verification_size: tuple[int, int],
) -> dict[int, OCRBlock]:
    verification_boxes = [
        _relative_bbox(block, verification_size) for block in verification
    ]
    used: set[int] = set()
    matches: dict[int, OCRBlock] = {}
    for primary_index, block in enumerate(primary):
        primary_box = _relative_bbox(block, primary_size)
        candidates = [
            (index, _iou(primary_box, verification_box))
            for index, verification_box in enumerate(verification_boxes)
            if index not in used
        ]
        if not candidates:
            continue
        match_index, overlap = max(candidates, key=lambda item: item[1])
        if overlap >= 0.35:
            matches[primary_index] = verification[match_index]
            used.add(match_index)
    return matches


def assess_ocr_page(
    primary: list[OCRBlock],
    verification: list[OCRBlock],
    *,
    primary_size: tuple[int, int],
    verification_size: tuple[int, int],
    min_confidence: float,
) -> ExtractionAssessment:
    """Check individual lines, then accept or reject complete source paragraphs."""
    matches = _match_blocks(primary, verification, primary_size, verification_size)
    records: list[dict] = []

    for index, block in enumerate(primary):
        matched = matches.get(index)
        reasons = []
        kind = "text"
        if block.confidence < min_confidence:
            reasons.append("ocr_low_confidence")
        if _formula_like(block.text):
            reasons.append("formula_detected")
            kind = "formula"
        elif _noise_like(block.text):
            reasons.append("noise_detected")
            kind = "noise"
        if matched is None:
            reasons.append("ocr_unstable")
        else:
            if matched.confidence < min_confidence:
                reasons.append("ocr_low_confidence")
            if _comparison_text(block.text) != _comparison_text(matched.text):
                reasons.append("ocr_unstable")

        records.append({
            "text": block.text,
            "confidence": block.confidence,
            "bbox": _relative_bbox(block, primary_size),
            "bbox_unit": "relative",
            "kind": kind,
            "decision": "rejected" if reasons else "accepted",
            "reasons": sorted(set(reasons)),
            "verification_text": matched.text if matched else None,
            "verification_confidence": matched.confidence if matched else None,
            "source_pass": "primary",
        })

    matched_verification_ids = {id(block) for block in matches.values()}
    for block in verification:
        if id(block) in matched_verification_ids or not block.text.strip():
            continue
        # A line missed by the primary pass must remain visible to the grouping
        # gate. It cannot itself be promoted into safe_text by verification.
        kind = "formula" if _formula_like(block.text) else (
            "noise" if _noise_like(block.text) else "text"
        )
        records.append({
            "text": block.text,
            "confidence": block.confidence,
            "bbox": _relative_bbox(block, verification_size),
            "bbox_unit": "relative",
            "kind": kind,
            "decision": "rejected",
            "reasons": ["ocr_missing_primary", "ocr_unstable"],
            "verification_text": block.text,
            "verification_confidence": block.confidence,
            "source_pass": "verification_only",
        })

    formula_present = any(record["kind"] == "formula" for record in records)
    if formula_present:
        for record in records:
            compact = re.sub(r"\s+", "", record["text"])
            if (
                record["kind"] == "text"
                and len(compact) <= 16
                and _SHORT_LATIN_RE.fullmatch(compact)
            ):
                record["kind"] = "formula"
                record["decision"] = "rejected"
                record["reasons"] = sorted(
                    set(record["reasons"] + ["formula_neighbor"])
                )

    formula_dependency = formula_present and any(
        _DEPENDENCY_RE.search(record["text"]) for record in records
    )
    if formula_dependency:
        for record in records:
            if record["decision"] == "accepted":
                record["decision"] = "rejected"
                record["reasons"] = ["formula_context_dependency"]

    raw_text = "\n".join(block.text for block in primary).strip()
    safe_text = apply_paragraph_gate(records, image_size=primary_size)
    reasons = sorted({reason for record in records for reason in record["reasons"]})
    if formula_dependency:
        reasons.append("formula_context_dependency")
    if not safe_text:
        reasons.append("no_safe_text")
        status = "rejected"
    elif any(record["decision"] == "rejected" for record in records):
        status = "partial"
    else:
        status = "accepted"

    return ExtractionAssessment(
        raw_text=raw_text,
        safe_text=safe_text,
        quality_status=status,
        quality_reasons=sorted(set(reasons)),
        confidence=(
            round(fmean(block.confidence for block in primary), 6)
            if primary
            else None
        ),
        blocks=records,
    )


def apply_paragraph_gate(records: list[dict], *, image_size: tuple[int, int]) -> str:
    """Annotate final decisions in-place; never emit only part of a source group.

    Line checks are kept for audit. Delimiter balance and leading-context checks
    apply to the complete paragraph so valid wrapped text is not judged in
    isolation. This is a rejection gate, not an OCR repair or semantic proof.
    """
    safe_paragraphs = []
    for number, indices in enumerate(group_source_paragraphs(records, image_size), 1):
        paragraph_text = "\n".join(records[index]["text"] for index in indices).strip()
        root_reasons = {reason for index in indices for reason in records[index]["reasons"]}
        gate_reasons = []
        if any(records[index]["decision"] == "rejected" for index in indices):
            gate_reasons.append("paragraph_member_rejected")
        if _unbalanced_delimiters(paragraph_text):
            gate_reasons.append("unbalanced_delimiters")
        if _CONTEXT_FRAGMENT_RE.search(paragraph_text):
            gate_reasons.append("context_fragment")
        decision = "rejected" if gate_reasons else "accepted"
        for index in indices:
            record = records[index]
            record["line_decision"] = record["decision"]
            record["line_reasons"] = list(record["reasons"])
            record["paragraph_id"] = f"p{number:03d}"
            record["paragraph_decision"] = decision
            record["paragraph_reasons"] = sorted(root_reasons | set(gate_reasons))
            record["paragraph_gate_version"] = PARAGRAPH_GATE_VERSION
            record["decision"] = decision
            record["reasons"] = sorted(set(record["reasons"]) | set(gate_reasons))
        if decision == "accepted":
            safe_paragraphs.append(paragraph_text)
    # Explicit separation prevents unrelated surviving paragraphs being read as
    # a single contiguous quotation after a rejected paragraph was removed.
    return "\n\n".join(safe_paragraphs)


__all__ = [
    "ExtractionAssessment", "PARAGRAPH_GATE_VERSION", "apply_paragraph_gate",
    "assess_ocr_page",
]
