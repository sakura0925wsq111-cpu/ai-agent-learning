"""Audit original provider trees without re-running or changing model output."""

import json
from pathlib import Path

from docling_core.types.doc import DoclingDocument

from run_candidates import BASE, normalize_docling, save, sha, summarize


def main():
    corpus = json.loads((BASE / "corpus.json").read_text(encoding="utf-8"))
    summary = []
    for case in corpus["cases"]:
        directory = BASE / "docling_run1" / case["id"]
        raw = directory / "provider_raw.json"
        normalized = normalize_docling(DoclingDocument.model_validate_json(raw.read_text(encoding="utf-8")))
        normalized.update({"case_id": case["id"], "provider_raw_sha256": sha(raw), "source_sha256": corpus["sources"][case["source"]]["sha256"]})
        destination = directory / "normalized_full.json"
        if destination.exists():
            raise FileExistsError(destination)
        save(destination, normalized)
        stats = summarize(normalized, case)
        stats["case_id"] = case["id"]
        summary.append(stats)
    save(BASE / "docling_run1" / "summary_full.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
