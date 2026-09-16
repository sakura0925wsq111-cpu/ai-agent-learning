"""Evaluate the current PPTX knowledge path on uncopied local source files."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from core.config import settings
from models.study import StudyDocument, StudyDocumentUnit
from services.study_knowledge import (
    LLMKnowledgeModel,
    extract_from_structured_document,
    structured_from_document_units,
)
from services.study_parser import parse_study_file


ROOT = Path(__file__).resolve().parents[2]


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: list[dict]) -> None:
    path.write_text("".join(json.dumps(value, ensure_ascii=False, default=str) + "\n" for value in values), encoding="utf-8")


def _structured(path: Path):
    digest = _sha(path)
    parsed = parse_study_file("pptx", path)
    document_id = str(uuid.uuid5(uuid.NAMESPACE_URL, digest))
    document = StudyDocument(
        id=document_id,
        user_id="evaluation-only",
        original_filename=path.name,
        file_type="pptx",
        storage_path=str(path),
        file_size=path.stat().st_size,
        sha256=digest,
        status="parsed",
        page_count=parsed.page_count,
    )
    units = [
        StudyDocumentUnit(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{digest}:{item.page_number}")),
            document_id=document_id,
            page_number=item.page_number,
            unit_index=index,
            unit_type=item.unit_type,
            raw_text=item.raw_text,
            normalized_text=item.normalized_text,
            safe_text=item.safe_text,
            text_hash=item.text_hash,
            extraction_method=item.extraction_method,
            ocr_confidence=item.ocr_confidence,
            ocr_blocks=item.ocr_blocks,
            quality_status=item.quality_status,
            quality_reasons=item.quality_reasons,
        )
        for index, item in enumerate(parsed.units)
    ]
    return document, structured_from_document_units(document, units)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, action="append", required=True)
    parser.add_argument("--repetitions", type=int, default=3, choices=(1, 2, 3))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    sources = []
    structured_documents = {}
    for source in args.source:
        if not source.is_file():
            raise FileNotFoundError(source)
        document, structured = _structured(source)
        sources.append({
            "filename": source.name,
            "sha256": document.sha256,
            "size": document.file_size,
            "slide_count": document.page_count,
            "split": "new_user_supplied_holdout",
            "original_file_copied": False,
        })
        structured_documents[document.sha256] = structured
        _write_json(
            args.output_dir / f"{document.sha256[:12]}-structured-document.json",
            {
                "revision_id": structured.revision_id,
                "source_sha256": structured.source_sha256,
                "parser_name": structured.parser_name,
                "parser_version": structured.parser_version,
                "parser_config": structured.parser_config,
                "blocks": [asdict(block) for block in structured.blocks],
            },
        )
    maximum_calls = sum(
        math.ceil(len(structured.blocks) / settings.study_knowledge_max_blocks_per_window) * 2
        for structured in structured_documents.values()
    ) * args.repetitions
    if maximum_calls > 50:
        raise ValueError("evaluation model-call bound exceeds 50")
    model = LLMKnowledgeModel()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()
    _write_json(args.output_dir / "manifest.json", {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "parser": "current production PPTX parser plus legacy-page-adapter-v1",
        "known_parser_limit": "Pictures and non-table relationships are not represented; missing geometry is unknown.",
        "model": model.model,
        "temperature": 0.0,
        "repetitions": args.repetitions,
        "maximum_model_calls": maximum_calls,
        "git_head": commit,
        "human_gold_complete": False,
        "accuracy_claim_allowed": False,
    })
    runs = []
    started_all = time.perf_counter()
    for repetition in range(1, args.repetitions + 1):
        for source in sources:
            structured = structured_documents[source["sha256"]]
            started = time.perf_counter()
            try:
                units, audit = extract_from_structured_document(structured, model)
                status, error = "completed", None
            except Exception as exc:
                units, audit = [], {}
                status, error = "failed", {"type": type(exc).__name__, "message": str(exc)}
            runs.append({
                "filename": source["filename"],
                "source_sha256": source["sha256"],
                "repetition": repetition,
                "status": status,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "units": units,
                "audit": audit,
                "error": error,
            })
            _write_jsonl(args.output_dir / "runs.jsonl", runs)
            print(json.dumps({
                "file": source["filename"], "repetition": repetition,
                "status": status, "candidates": len(units),
                "usable": sum(item["disposition"] == "usable" for item in units),
                "calls": audit.get("model_call_count", 0),
            }, ensure_ascii=False), flush=True)
    counts = Counter(unit["disposition"] for run in runs for unit in run["units"])
    signatures = defaultdict(list)
    for run in runs:
        signatures[run["filename"]].append({
            (unit["knowledge_type"], unit["disposition"], tuple(
                (ref["page_number"], ref["block_id"], ref["char_start"], ref["char_end"])
                for ref in unit["source_refs"]
            )) for unit in run["units"]
        })
    summary = {
        "run_count": len(runs),
        "completed_run_count": sum(run["status"] == "completed" for run in runs),
        "actual_model_call_count": sum(run["audit"].get("model_call_count", 0) for run in runs),
        "candidate_count": sum(len(run["units"]) for run in runs),
        "disposition_counts": dict(counts),
        "exact_source_count": sum(unit["check_meta"].get("exact_slice") is True for run in runs for unit in run["units"]),
        "files": {
            name: {
                "stable": all(value == values[0] for value in values[1:]),
                "signature_counts": [len(value) for value in values],
            } for name, values in signatures.items()
        },
        "elapsed_seconds": round(time.perf_counter() - started_all, 3),
        "manual_precision": None,
        "gold_coverage": None,
    }
    _write_json(args.output_dir / "summary.json", summary)
    _write_jsonl(args.output_dir / "manual_review_template.jsonl", [
        {
            "filename": run["filename"],
            "knowledge_type": unit["knowledge_type"],
            "content": unit["content"],
            "disposition": unit["disposition"],
            "source_refs": unit["source_refs"],
            "machine_reasons": unit["reasons"],
            "human_label": None,
            "human_notes": "",
        }
        for run in runs if run["repetition"] == 1 for unit in run["units"]
    ])
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
