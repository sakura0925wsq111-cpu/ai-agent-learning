"""Evaluate source-ID knowledge V2 against the frozen PPT regression gold."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from services.study_knowledge import StructuredDocument
from services.study_knowledge_v2 import LLMKnowledgeModelV2, extract_from_numbered_document
from services.study_source_units import structured_from_pptx


SOURCE_MAP = {
    "10.4  道路交通振动的防治.ppt": "10.4-road-vibration.pptx",
    "11.1 概述.ppt": "11.1-overview.pptx",
    "11.4道路结构物景观与绿化设计.ppt": "11.4-structures-landscape.pptx",
    "11.5 道路铺装景观.ppt": "11.5-pavement-landscape.pptx",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"[\s，,。；;：（）():、]", "", text)


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: list[dict]) -> None:
    path.write_text("".join(json.dumps(value, ensure_ascii=False, default=str) + "\n" for value in values), encoding="utf-8")


def _subset(document: StructuredDocument, pages: set[int], label: str) -> StructuredDocument:
    blocks = [
        block for block in document.blocks
        if block.source_spans and block.source_spans[0].page_number in pages
    ]
    return replace(
        document,
        revision_id=hashlib.sha256(
            f"{document.revision_id}|{label}|{sorted(pages)}".encode("utf-8")
        ).hexdigest(),
        blocks=blocks,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=3, choices=(1, 2, 3))
    parser.add_argument("--skip-negative-control", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)

    gold = [
        json.loads(line)
        for line in (args.base_dir / "assistant_visual_gold.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    gold_by_source: dict[str, list[dict]] = defaultdict(list)
    for item in gold:
        gold_by_source[item["source"]].append(item)

    documents = {}
    for source_name, filename in SOURCE_MAP.items():
        path = args.base_dir / "converted" / filename
        documents[source_name] = structured_from_pptx(path, source_sha256=_sha(path))

    model = LLMKnowledgeModelV2()
    maximum_calls = sum(
        len({item["page_number"] for item in items}) + 1
        for items in gold_by_source.values()
    ) * args.repetitions + (0 if args.skip_negative_control else 6)
    if maximum_calls > 50:
        raise ValueError("model_call_bound_exceeds_50")
    _write_json(args.output_dir / "manifest.json", {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "method": "stable source IDs selected by model; content rebuilt by code",
        "model": model.model,
        "repetitions": args.repetitions,
        "gold_count": len(gold),
        "gold_review": "assistant_visual",
        "maximum_model_calls": maximum_calls,
        "negative_control": (
            None if args.skip_negative_control
            else "11.4道路结构物景观与绿化设计.ppt, one run"
        ),
        "accuracy_claim_allowed": False,
    })

    runs = []
    started = time.perf_counter()
    for repetition in range(1, args.repetitions + 1):
        for source_name, gold_items in gold_by_source.items():
            pages = {item["page_number"] for item in gold_items}
            document = _subset(documents[source_name], pages, f"gold-r{repetition}")
            records, audit = extract_from_numbered_document(document, model)
            for record in records:
                record_pages = sorted({ref["page_number"] for ref in record["source_refs"]})
                matched_gold = [
                    item["gold_id"] for item in gold_items
                    if item["type"] == record["knowledge_type"]
                    and item["page_number"] in record_pages
                    and _normalized(item["content"]) == _normalized(record["content"])
                ]
                record["matched_gold_ids"] = matched_gold
            runs.append({
                "source": source_name,
                "repetition": repetition,
                "pages": sorted(pages),
                "records": records,
                "audit": audit,
            })
            _write_jsonl(args.output_dir / "runs.jsonl", runs)
            print(json.dumps({
                "source": source_name,
                "repetition": repetition,
                "candidates": len(records),
                "usable": sum(item["disposition"] == "usable" for item in records),
                "matched_gold": len({gold_id for item in records for gold_id in item["matched_gold_ids"]}),
                "calls": audit["model_call_count"],
            }, ensure_ascii=False), flush=True)

    negative_records = []
    if not args.skip_negative_control:
        negative_name = "11.4道路结构物景观与绿化设计.ppt"
        negative_records, negative_audit = extract_from_numbered_document(
            documents[negative_name], model
        )
        runs.append({
            "source": negative_name,
            "repetition": 1,
            "pages": sorted({span.page_number for block in documents[negative_name].blocks for span in block.source_spans}),
            "negative_control": True,
            "records": negative_records,
            "audit": negative_audit,
        })
    _write_jsonl(args.output_dir / "runs.jsonl", runs)

    evaluation_runs = [run for run in runs if not run.get("negative_control")]
    usable = [
        record for run in evaluation_runs for record in run["records"]
        if record["disposition"] == "usable"
    ]
    correct_usable = [record for record in usable if record["matched_gold_ids"]]
    matched_opportunities = sum(
        len({gold_id for record in run["records"] for gold_id in record["matched_gold_ids"]})
        for run in evaluation_runs
    )
    total_opportunities = len(gold) * args.repetitions
    signatures: dict[str, list[set[tuple]]] = defaultdict(list)
    for run in evaluation_runs:
        signatures[run["source"]].append({
            (
                record["knowledge_type"],
                record["disposition"],
                tuple(record["check_meta"]["source_ids"]),
            )
            for record in run["records"]
        })
    counts = Counter(
        record["disposition"] for run in runs for record in run["records"]
    )
    summary = {
        "evaluation_run_count": len(evaluation_runs),
        "negative_control_run_count": 0 if args.skip_negative_control else 1,
        "actual_model_call_count": sum(run["audit"]["model_call_count"] for run in runs),
        "candidate_count": sum(len(run["records"]) for run in runs),
        "disposition_counts": dict(counts),
        "gold_count": len(gold),
        "gold_opportunities_across_repetitions": total_opportunities,
        "matched_gold_opportunities": matched_opportunities,
        "coverage": round(matched_opportunities / total_opportunities, 4) if total_opportunities else None,
        "usable_count": len(usable),
        "correct_usable_count": len(correct_usable),
        "usable_precision": round(len(correct_usable) / len(usable), 4) if usable else None,
        "negative_control_candidate_count": len(negative_records),
        "negative_control_usable_count": sum(item["disposition"] == "usable" for item in negative_records),
        "stability": {
            source: {
                "stable": all(value == values[0] for value in values[1:]),
                "signature_counts": [len(value) for value in values],
            }
            for source, values in signatures.items()
        },
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "limitations": [
            "Gold labels are assistant visual review, not independent human labels.",
            "Only pages containing known gold were repeated three times.",
            "No page images were sent to the current text-only model.",
        ],
    }
    _write_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
