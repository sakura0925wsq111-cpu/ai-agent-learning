"""Smoke-test the direct Doubao document pipeline without writing database rows."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pymupdf


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from models.study import StudyDocument
from services.study_knowledge_doubao import _source_as_pdf, extract_direct_document


def _subset_pdf(source: Path, page_count: int) -> Path:
    handle, name = tempfile.mkstemp(suffix=".pdf")
    os.close(handle)
    Path(name).unlink(missing_ok=True)
    target = Path(name)
    document = pymupdf.open(source)
    subset = pymupdf.open()
    try:
        subset.insert_pdf(
            document,
            from_page=0,
            to_page=min(page_count, document.page_count) - 1,
        )
        subset.save(target)
    finally:
        subset.close()
        document.close()
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--first-pages", type=int, default=None)
    parser.add_argument("--sample-count", type=int, default=8)
    parser.add_argument("--report-path", type=Path, default=None)
    parser.add_argument("--render-only", action="store_true")
    args = parser.parse_args()

    if not args.source.is_file():
        raise FileNotFoundError(args.source)
    if args.first_pages is not None and args.first_pages < 1:
        raise ValueError("--first-pages must be positive")

    if args.render_only:
        with _source_as_pdf(args.source) as pdf_path:
            with pymupdf.open(pdf_path) as rendered:
                print(json.dumps({
                    "page_count": rendered.page_count,
                    "page_text_lengths": [len(page.get_text()) for page in rendered],
                }, ensure_ascii=False))
        return

    processing_path = args.source
    temporary = None
    if args.first_pages is not None:
        if args.source.suffix.lower() != ".pdf":
            raise ValueError("--first-pages currently supports PDF only")
        temporary = _subset_pdf(args.source, args.first_pages)
        processing_path = temporary

    try:
        file_type = args.source.suffix.lower().removeprefix(".")
        digest = hashlib.sha256(processing_path.read_bytes()).hexdigest()
        source = StudyDocument(
            id="smoke",
            user_id="smoke",
            original_filename=args.source.name,
            file_type=file_type,
            storage_path=str(processing_path),
            file_size=processing_path.stat().st_size,
            sha256=digest,
            status="uploaded",
        )
        records, audit, _ = extract_direct_document(source, processing_path)
        if args.report_path is not None:
            args.report_path.parent.mkdir(parents=True, exist_ok=True)
            args.report_path.write_text(
                json.dumps({"records": records, "audit": audit}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        print(json.dumps({
            "candidate_count": audit["candidate_count"],
            "accepted_count": audit["accepted_count"],
            "filtered_count": audit["filtered_count"],
            "filtered_by_reason": audit["filtered_by_reason"],
            "remote_file_deleted": audit["remote_file_deleted"],
            "samples": [
                {
                    "type": item["knowledge_type"],
                    "page_or_slide": item["source_refs"][0]["page_number"],
                    "confidence": item["extraction_meta"]["confidence"],
                    "content": item["content"][:160],
                }
                for item in records[:args.sample_count]
            ],
        }, ensure_ascii=False, indent=2))
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
