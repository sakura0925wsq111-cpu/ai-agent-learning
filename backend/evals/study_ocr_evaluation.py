"""Run a reproducible page-level OCR quality evaluation."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import pymupdf

from core.config import settings
from services.study_extraction_quality import PARAGRAPH_GATE_VERSION
from services.study_files import sha256_file
from services.study_parser import StudyParseError, parse_study_file


def _parse_pages(value: str) -> list[int]:
    pages = sorted({int(item.strip()) for item in value.split(",") if item.strip()})
    if not pages or any(page < 1 for page in pages):
        raise argparse.ArgumentTypeError("pages must be positive comma-separated integers")
    return pages


def _git_head(project_root: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def run_evaluation(source: Path, pages: list[int], output_dir: Path) -> None:
    source = source.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    pages_path = output_dir / "machine_pages.jsonl"
    manifest_path = output_dir / "manifest.json"
    summary_path = output_dir / "machine_summary.json"
    if any(path.exists() for path in (pages_path, manifest_path, summary_path)):
        raise FileExistsError(
            f"evaluation output already exists in {output_dir}; choose a new directory"
        )

    with pymupdf.open(source) as document:
        page_count = len(document)
    if any(page > page_count for page in pages):
        raise ValueError(f"page selection exceeds document page count {page_count}")

    project_root = Path(__file__).resolve().parents[2]
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "filename": source.name,
            "sha256": sha256_file(source),
            "size_bytes": source.stat().st_size,
            "page_count": page_count,
        },
        "selected_pages": pages,
        "selection_method": "explicit fixed page list",
        "pipeline": {
            "pymupdf": version("PyMuPDF"),
            "paddleocr": version("paddleocr"),
            "paddlepaddle": version("paddlepaddle"),
            "primary_dpi": settings.study_ocr_dpi,
            "verification_dpi": settings.study_ocr_verify_dpi,
            "minimum_confidence": settings.study_ocr_min_confidence,
            "device": settings.study_ocr_device,
            "detection_model": "PP-OCRv5_mobile_det",
            "recognition_model": "PP-OCRv5_mobile_rec",
            "llm_used": False,
            "paragraph_gate_version": PARAGRAPH_GATE_VERSION,
        },
        "code": {
            "git_head": _git_head(project_root),
            "note": "Study OCR changes may be uncommitted; preserve this dataset with its code diff.",
            "source_sha256": {
                name: sha256_file(project_root / "backend" / "services" / name)
                for name in (
                    "study_parser.py", "study_ocr.py", "study_extraction_quality.py",
                    "study_paragraphs.py",
                )
            },
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    results = []
    for position, page_number in enumerate(pages, start=1):
        started = time.perf_counter()
        try:
            parsed = parse_study_file(
                "pdf",
                source,
                page_numbers=[page_number],
            )
            unit = parsed.units[0]
            result = {
                "page_number": page_number,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "status": "ok",
                "extraction_method": unit.extraction_method,
                "ocr_confidence": unit.ocr_confidence,
                "quality_status": unit.quality_status,
                "quality_reasons": unit.quality_reasons,
                "raw_text": unit.raw_text,
                "safe_text": unit.safe_text,
                "ocr_blocks": unit.ocr_blocks,
            }
        except StudyParseError as exc:
            result = {
                "page_number": page_number,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "status": "error",
                "error_code": exc.code,
                "error_message": exc.message,
            }
        results.append(result)
        print(
            f"[{position}/{len(pages)}] page={page_number} "
            f"status={result.get('quality_status', result['status'])} "
            f"seconds={result['elapsed_seconds']}", flush=True,
        )

    with pages_path.open("x", encoding="utf-8", newline="\n") as output:
        for result in results:
            output.write(json.dumps(result, ensure_ascii=False) + "\n")

    successful = [item for item in results if item["status"] == "ok"]
    quality_counts = Counter(item["quality_status"] for item in successful)
    block_decisions = Counter(
        block["decision"]
        for item in successful
        for block in item["ocr_blocks"]
    )
    reason_counts = Counter(
        reason
        for item in successful
        for reason in item["quality_reasons"]
    )
    raw_characters = sum(len(item["raw_text"]) for item in successful)
    safe_characters = sum(len(item["safe_text"]) for item in successful)
    summary = {
        "selected_page_count": len(pages),
        "successful_page_count": len(successful),
        "error_page_count": len(results) - len(successful),
        "quality_status_counts": dict(sorted(quality_counts.items())),
        "block_decision_counts": dict(sorted(block_decisions.items())),
        "quality_reason_counts": dict(sorted(reason_counts.items())),
        "raw_character_count": raw_characters,
        "safe_character_count": safe_characters,
        "safe_character_retention": (
            round(safe_characters / raw_characters, 4) if raw_characters else 0.0
        ),
        "total_elapsed_seconds": round(
            sum(item["elapsed_seconds"] for item in results), 3
        ),
        "manual_review_complete": False,
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--pages", type=_parse_pages, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run_evaluation(args.source, args.pages, args.output_dir)


if __name__ == "__main__":
    main()
