"""Replay saved model payloads through the current deterministic knowledge gates."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from services.study_knowledge import ModelResult, extract_from_structured_document, load_docling_snapshot


PARSER_BASE = Path(__file__).resolve().parent / "parser_selection" / "2026-09-04"


class ReplayModel:
    def __init__(self, model: str, extraction: dict, review: dict | None) -> None:
        self.model = model
        self._extraction = extraction
        self._review = review or {"decisions": []}

    def extract(self, blocks):
        return ModelResult(
            payload=self._extraction, model=self.model, duration_ms=0.0, call_count=0
        )

    def review(self, blocks, candidates):
        candidate_ids = {item["candidate_id"] for item in candidates}
        payload = {
            "decisions": [
                item for item in self._review.get("decisions", [])
                if item.get("candidate_id") in candidate_ids
            ]
        }
        return ModelResult(payload=payload, model=self.model, duration_ms=0.0, call_count=0)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(value, ensure_ascii=False) + "\n" for value in values),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-runs", type=Path, action="append", required=True)
    parser.add_argument("--cases", default="")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    selected = {item.strip() for item in args.cases.split(",") if item.strip()}
    output = []
    for source_path in args.input_runs:
        for saved in _jsonl(source_path):
            if saved.get("status") != "completed":
                continue
            case_id = saved["case_id"]
            if selected and case_id not in selected:
                continue
            batch = next(
                (
                    item for item in saved["audit"].get("candidate_batches", [])
                    if item.get("stage") == "complete"
                ),
                None,
            )
            if batch is None:
                continue
            snapshot = PARSER_BASE / "docling_run1" / case_id / "normalized_full.json"
            structured = load_docling_snapshot(
                snapshot, expected_source_sha256=saved["source_sha256"]
            )
            model = ReplayModel(
                saved["audit"].get("model", "saved-model"),
                batch["extract_payload"],
                batch.get("review_payload"),
            )
            units, audit = extract_from_structured_document(
                structured, model, max_model_calls=2
            )
            output.append({
                "case_id": case_id,
                "repetition": saved["repetition"],
                "source_sha256": saved["source_sha256"],
                "units": units,
                "audit": audit,
                "replayed_from": str(source_path),
            })
    _write_jsonl(args.output_dir / "replayed_runs.jsonl", output)
    counts = Counter(unit["disposition"] for run in output for unit in run["units"])
    signatures: dict[str, list[set[tuple]]] = defaultdict(list)
    for run in output:
        signatures[run["case_id"]].append({
            (
                unit["knowledge_type"], unit["disposition"],
                tuple((ref["page_number"], ref["block_id"], ref["char_start"], ref["char_end"])
                      for ref in unit["source_refs"]),
            )
            for unit in run["units"]
        })
    summary = {
        "replayed_run_count": len(output),
        "model_call_count": 0,
        "candidate_count": sum(len(run["units"]) for run in output),
        "disposition_counts": dict(counts),
        "exact_source_count": sum(
            unit["check_meta"].get("exact_slice") is True
            for run in output for unit in run["units"]
        ),
        "cases": {
            case_id: {
                "stable": bool(values) and all(value == values[0] for value in values[1:]),
                "signature_counts": [len(value) for value in values],
            }
            for case_id, values in signatures.items()
        },
        "note": "Saved model payloads and review decisions; current deterministic gates; zero new model calls.",
    }
    _write_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
