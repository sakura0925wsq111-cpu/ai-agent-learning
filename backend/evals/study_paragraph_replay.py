"""Compare paragraph-only gating with a frozen OCR baseline, without re-OCR."""

from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

from services.study_extraction_quality import PARAGRAPH_GATE_VERSION, apply_paragraph_gate
from services.study_files import sha256_file


def run_replay(source: Path, baseline_dir: Path, output_dir: Path) -> dict:
    baseline_path = baseline_dir / "machine_pages.jsonl"
    manifest = json.loads((baseline_dir / "manifest.json").read_text(encoding="utf-8"))
    if sha256_file(source) != manifest["source"]["sha256"]:
        raise ValueError("source PDF does not match the evaluation baseline")
    baseline_hash = sha256_file(baseline_path)
    baseline = [json.loads(line) for line in baseline_path.read_text(encoding="utf-8").splitlines()]
    output_dir.mkdir(parents=True, exist_ok=False)
    comparison = []
    before_counts: Counter = Counter()
    after_counts: Counter = Counter()
    with pymupdf.open(source) as document:
        scale = manifest["pipeline"]["primary_dpi"] / 72
        for page in baseline:
            if page["status"] != "ok":
                comparison.append({
                    "page_number": page["page_number"], "status": "baseline_error",
                    "error_code": page["error_code"],
                })
                continue
            records = copy.deepcopy(page["ocr_blocks"])
            rect = (document[page["page_number"] - 1].rect * pymupdf.Matrix(scale, scale)).irect
            safe_text = apply_paragraph_gate(records, image_size=(rect.width, rect.height))
            new_status = "rejected" if not safe_text else (
                "partial" if any(block["decision"] == "rejected" for block in records)
                else "accepted"
            )
            before_counts.update(block["decision"] for block in page["ocr_blocks"])
            after_counts.update(block["decision"] for block in records)
            comparison.append({
                "page_number": page["page_number"], "status": "ok",
                "before_quality_status": page["quality_status"],
                "after_quality_status": new_status,
                "before_safe_text": page["safe_text"], "after_safe_text": safe_text,
                "ocr_blocks": records,
            })
    if sha256_file(baseline_path) != baseline_hash:
        raise RuntimeError("baseline changed during replay")
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "paragraph_gate_version": PARAGRAPH_GATE_VERSION,
        "source": manifest["source"], "baseline_sha256": baseline_hash,
        "method": (
            "Apply paragraph grouping only to frozen line-level decisions. "
            "No new OCR, no promotion of rejected baseline lines, no independent accuracy estimate. "
            "The old dataset does not contain unmatched verification-only boxes."
        ),
        "before_block_decisions": dict(before_counts),
        "after_block_decisions": dict(after_counts),
        "after_page_statuses": dict(Counter(
            item.get("after_quality_status", "baseline_error") for item in comparison
        )),
        "baseline_preserved": True,
    }
    with (output_dir / "comparison.jsonl").open("x", encoding="utf-8") as output:
        for item in comparison:
            output.write(json.dumps(item, ensure_ascii=False) + "\n")
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_replay(args.source, args.baseline_dir, args.output_dir), ensure_ascii=False))
