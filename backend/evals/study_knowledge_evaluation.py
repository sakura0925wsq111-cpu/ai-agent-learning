"""Reproducible knowledge extraction evaluation on frozen Docling snapshots.

This script stores private derived text locally under an ignored output folder.
It does not create human labels or claim an accuracy percentage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from core.config import settings
from services.study_knowledge import (
    LLMKnowledgeModel,
    PIPELINE_VERSION,
    extract_from_structured_document,
    load_docling_snapshot,
)


ROOT = Path(__file__).resolve().parents[2]
PARSER_BASE = Path(__file__).resolve().parent / "parser_selection" / "2026-09-04"
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "study_knowledge"


def _write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, values: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(value, ensure_ascii=False, default=str) + "\n" for value in values),
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _stability(records: list[dict]) -> dict:
    grouped: dict[str, list[set[tuple]]] = defaultdict(list)
    for item in records:
        key = item["case_id"]
        signature = {
            (
                unit["knowledge_type"],
                unit["disposition"],
                tuple(
                    (ref["page_number"], ref["block_id"], ref["char_start"], ref["char_end"])
                    for ref in unit["source_refs"]
                ),
            )
            for unit in item["units"]
        }
        grouped[key].append(signature)
    return {
        case_id: {
            "repetition_count": len(signatures),
            "stable": bool(signatures) and all(value == signatures[0] for value in signatures[1:]),
            "signature_counts": [len(value) for value in signatures],
        }
        for case_id, signatures in grouped.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.repetitions < 1 or args.repetitions > 3:
        raise ValueError("repetitions must be between 1 and 3")

    corpus_path = PARSER_BASE / "corpus.json"
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    available = {case["id"]: case for case in corpus["cases"]}
    case_ids = list(available) if not args.cases else [
        value.strip() for value in args.cases.split(",") if value.strip()
    ]
    unknown = set(case_ids) - set(available)
    if unknown:
        raise ValueError(f"unknown cases: {sorted(unknown)}")
    maximum_calls = len(case_ids) * args.repetitions * 2
    if maximum_calls > 48:
        raise ValueError(f"preflight model-call bound {maximum_calls} exceeds 48")

    stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / f"{stamp}-docling-knowledge-v1"
    output_dir.mkdir(parents=True, exist_ok=False)
    model = LLMKnowledgeModel()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": PIPELINE_VERSION,
        "model": model.model,
        "provider_base_host": settings.llm_base_url.split("://")[-1].split("/")[0],
        "configured_credential": bool(settings.llm_api_key),
        "temperature": 0.0,
        "repetitions": args.repetitions,
        "case_ids": case_ids,
        "maximum_model_calls": maximum_calls,
        "corpus_path": str(corpus_path.relative_to(ROOT)),
        "corpus_sha256": _sha(corpus_path),
        "git_head": commit,
        "sample_role": "development plus engineering holdout as registered in corpus.json",
        "human_gold_complete": False,
        "accuracy_claim_allowed": False,
        "privacy": "Derived private lesson text remains in the local ignored evaluation directory.",
        "sources": corpus["sources"],
    }
    _write_json(output_dir / "manifest.json", manifest)

    evaluations: list[dict] = []
    started_all = time.perf_counter()
    for repetition in range(1, args.repetitions + 1):
        for case_id in case_ids:
            case = available[case_id]
            source = corpus["sources"][case["source"]]
            snapshot_path = (
                PARSER_BASE / "docling_run1" / case_id / "normalized_full.json"
            )
            started = time.perf_counter()
            try:
                structured = load_docling_snapshot(
                    snapshot_path,
                    expected_source_sha256=source["sha256"],
                )
                units, audit = extract_from_structured_document(
                    structured,
                    model,
                    max_model_calls=2,
                )
                status = "completed"
                error = None
            except Exception as exc:
                units, audit = [], {}
                status = "failed"
                error = {"type": type(exc).__name__, "message": str(exc)}
            record = {
                "case_id": case_id,
                "source_key": case["source"],
                "source_sha256": source["sha256"],
                "pages": case["pages"],
                "repetition": repetition,
                "status": status,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "error": error,
                "baseline_supported_block_count": sum(
                    block.type in {"paragraph", "list", "list_item"}
                    for block in structured.blocks
                ) if status == "completed" else None,
                "units": units,
                "audit": audit,
            }
            evaluations.append(record)
            _write_jsonl(output_dir / "runs.jsonl", evaluations)
            print(
                json.dumps({
                    "case": case_id,
                    "repetition": repetition,
                    "status": status,
                    "candidates": len(units),
                    "usable": sum(item["disposition"] == "usable" for item in units),
                    "calls": audit.get("model_call_count", 0),
                }, ensure_ascii=False),
                flush=True,
            )

    disposition_counts = Counter(
        unit["disposition"] for run in evaluations for unit in run["units"]
    )
    actual_calls = sum(run["audit"].get("model_call_count", 0) for run in evaluations)
    stability = _stability(evaluations)
    summary = {
        "run_count": len(evaluations),
        "completed_run_count": sum(run["status"] == "completed" for run in evaluations),
        "failed_run_count": sum(run["status"] == "failed" for run in evaluations),
        "actual_model_call_count": actual_calls,
        "maximum_model_calls": maximum_calls,
        "candidate_count": sum(len(run["units"]) for run in evaluations),
        "disposition_counts": dict(disposition_counts),
        "source_slice_exact_count": sum(
            unit["check_meta"].get("exact_slice") is True
            for run in evaluations for unit in run["units"]
        ),
        "usable_source_ref_count": sum(
            bool(unit["source_refs"])
            for run in evaluations for unit in run["units"]
            if unit["disposition"] == "usable"
        ),
        "usable_unit_count": disposition_counts.get("usable", 0),
        "formula_or_unsupported_usable_count": sum(
            unit["disposition"] == "usable"
            and any("formula" in reason or "unsupported" in reason for reason in unit["reasons"])
            for run in evaluations for unit in run["units"]
        ),
        "stability": stability,
        "stable_case_count": sum(item["stable"] for item in stability.values()),
        "case_count": len(stability),
        "total_elapsed_seconds": round(time.perf_counter() - started_all, 3),
        "human_gold_complete": False,
        "manual_precision": None,
        "coverage_against_gold": None,
        "interpretation": (
            "Source and stability metrics are machine checks. Precision and coverage remain "
            "unset until independent manual labels exist."
        ),
    }
    _write_json(output_dir / "summary.json", summary)

    review_rows = []
    for run in evaluations:
        if run["repetition"] != 1:
            continue
        for unit in run["units"]:
            review_rows.append({
                "case_id": run["case_id"],
                "knowledge_type": unit["knowledge_type"],
                "content": unit["content"],
                "disposition": unit["disposition"],
                "source_refs": unit["source_refs"],
                "machine_reasons": unit["reasons"],
                "human_label": None,
                "human_error_types": [],
                "human_notes": "",
            })
    _write_jsonl(output_dir / "manual_review_template.jsonl", review_rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
