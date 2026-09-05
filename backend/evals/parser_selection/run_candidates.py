"""Isolated structural parser probes. This does not create usable business Units."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import sys
import time
import traceback
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BASE = Path(__file__).resolve().parent / "2026-09-04"
TYPE_MAP = {
    "text": "paragraph", "paragraph": "paragraph", "title": "heading", "section_header": "heading",
    "doc_title": "heading", "paragraph_title": "heading", "list_item": "list_item",
    "table": "table", "formula": "formula", "equation": "formula", "image": "figure",
    "picture": "figure", "figure": "figure", "chart": "figure", "caption": "caption",
    "figure_title": "caption", "figure_caption": "caption", "figure_table_title": "caption",
    "table_caption": "caption", "page_header": "furniture", "page_footer": "furniture",
    "header": "furniture", "footer": "furniture", "number": "furniture", "page_number": "furniture",
}


def sha(path):
    with Path(path).open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def clean(value):
    if hasattr(value, "tolist"):
        return clean(value.tolist())
    if isinstance(value, dict):
        return {str(key): clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def save(path, value):
    Path(path).write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def disposition(kind):
    # No candidate is promoted to usable merely because the provider called it text.
    return "unsupported" if kind in {"formula", "table", "figure", "caption", "furniture"} else "uncertain"


def normalize_docling(document):
    """Preserve every content node, including children inside pictures/tables."""
    order_map = {}
    for root in (document.body, document.furniture):
        for item, level in document.iterate_items(root=root, traverse_pictures=True):
            order_map[item.self_ref] = (len(order_map), level)
    blocks = []
    for item in [*document.texts, *document.tables, *document.pictures]:
        label = str(getattr(item.label, "value", item.label))
        spans = []
        for provenance in item.prov:
            page = document.pages[provenance.page_no]
            width, height = page.size.width, page.size.height
            box = provenance.bbox
            left, right = min(box.l, box.r), max(box.l, box.r)
            if "BOTTOM" in str(box.coord_origin).upper():
                top, bottom = height - max(box.t, box.b), height - min(box.t, box.b)
            else:
                top, bottom = min(box.t, box.b), max(box.t, box.b)
            spans.append({"page_number": provenance.page_no,
                          "bbox": [left/width, top/height, right/width, bottom/height],
                          "character_span": list(provenance.charspan)})
        kind = TYPE_MAP.get(label, "unknown")
        order, level = order_map.get(item.self_ref, (None, None))
        blocks.append({
            "id": item.self_ref, "type": kind, "provider_label": label,
            "text": getattr(item, "text", ""), "raw_text": getattr(item, "orig", ""),
            "reading_order": order, "level": level,
            "parent_id": item.parent.cref if item.parent else None,
            "children": [ref.cref for ref in item.children],
            "source_spans": spans, "disposition": disposition(kind), "completeness": "unknown",
        })
    blocks.sort(key=lambda block: block["reading_order"] if block["reading_order"] is not None else float("inf"))
    containers = [{"id": node.self_ref, "label": str(getattr(node.label, "value", node.label)),
                   "parent_id": node.parent.cref if node.parent else None,
                   "children": [ref.cref for ref in node.children]}
                  for node in [document.body, document.furniture, *document.groups]]
    return {"blocks": blocks, "containers": containers, "adapter_version": "docling-full-tree-v2",
            "missing_features": ["unit_completeness", "independent_text_verification"]}


class DoclingProbe:
    def __init__(self):
        from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        options = PdfPipelineOptions(
            do_ocr=True, do_table_structure=False, do_formula_enrichment=False,
            do_code_enrichment=False, do_picture_description=False,
            enable_remote_services=False, allow_external_plugins=False,
            ocr_options=RapidOcrOptions(backend="onnxruntime", lang=["ch", "en"]),
            accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU, num_threads=4),
            document_timeout=180,
        )
        self.config = options.model_dump(mode="json")
        self.converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
        self.converter.initialize_pipeline(InputFormat.PDF)

    def convert(self, source, pages, output_dir):
        result = self.converter.convert(source, page_range=(min(pages), max(pages)))
        document = result.document
        save(output_dir / "provider_raw.json", document.export_to_dict())
        (output_dir / "preview.md").write_text(document.export_to_markdown(), encoding="utf-8")
        save(output_dir / "provider_confidence.json", result.confidence.model_dump(mode="json"))
        normalized = normalize_docling(document)
        normalized["provider_status"] = str(result.status)
        return normalized


class PaddleProbe:
    def __init__(self):
        from paddleocr import PPStructureV3
        self.config = {
            "layout_detection_model_name": "PP-DocLayout_plus-L",
            "text_detection_model_name": "PP-OCRv5_mobile_det",
            "text_recognition_model_name": "PP-OCRv5_mobile_rec",
            "use_doc_orientation_classify": False, "use_doc_unwarping": False,
            "use_textline_orientation": False, "use_formula_recognition": False,
            "use_table_recognition": False, "use_seal_recognition": False,
            "use_chart_recognition": False, "use_region_detection": False,
            "device": "cpu", "cpu_threads": 4, "enable_mkldnn": False,
        }
        self.pipeline = PPStructureV3(**self.config)

    def convert(self, source, pages, output_dir):
        import numpy as np
        import pymupdf
        blocks = []
        raw_pages = []
        with pymupdf.open(source) as document:
            for page_number in pages:
                pix = document[page_number - 1].get_pixmap(dpi=200, colorspace=pymupdf.csRGB, alpha=False)
                image = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)
                results = list(self.pipeline.predict(image))
                for result in results:
                    payload = result.json
                    if callable(payload):
                        payload = payload()
                    payload = clean(payload)
                    data = payload.get("res", payload)
                    raw_pages.append({"original_page_number": page_number, "result": data})
                    for sequence, item in enumerate(data.get("parsing_res_list", [])):
                        label = item.get("block_label", "unknown")
                        kind = TYPE_MAP.get(label, "unknown")
                        box = item.get("block_bbox")
                        spans = [] if box is None else [{
                            "page_number": page_number,
                            "bbox": [box[0]/pix.width, box[1]/pix.height, box[2]/pix.width, box[3]/pix.height],
                            "character_span": None,
                        }]
                        blocks.append({
                            "id": f"p{page_number}:b{sequence}", "type": kind,
                            "provider_label": label, "text": item.get("block_content", ""),
                            "reading_order": item.get("block_order"), "provider_sequence": sequence,
                            "parent_id": None, "children": [], "source_spans": spans,
                            "disposition": disposition(kind), "completeness": "unknown",
                        })
                del image, pix
        save(output_dir / "provider_raw.json", raw_pages)
        return {"blocks": blocks, "containers": [], "provider_status": "completed",
                "missing_features": ["explicit_hierarchy", "unit_completeness", "independent_text_verification"]}


def summarize(normalized, case):
    blocks = normalized["blocks"]
    invalid, missing = [], []
    for block in blocks:
        if not block["source_spans"]:
            missing.append(block["id"])
        for span in block["source_spans"]:
            box = span["bbox"]
            if (span["page_number"] not in case["pages"] or len(box) != 4
                or not all(-0.0001 <= value <= 1.0001 for value in box)
                or box[0] >= box[2] or box[1] >= box[3]):
                invalid.append(block["id"])
    text = "".join(str(block["text"]) for block in blocks)
    compact = "".join(unicodedata.normalize("NFKC", text).split())
    return {
        "block_count": len(blocks), "type_counts": dict(Counter(block["type"] for block in blocks)),
        "missing_provenance_ids": missing, "invalid_provenance_ids": sorted(set(invalid)),
        "blocks_with_parent": sum(block["parent_id"] is not None for block in blocks),
        "container_count": len(normalized["containers"]),
        "cross_page_block_count": sum(len({span['page_number'] for span in block['source_spans']}) > 1 for block in blocks),
        "anchor_presence": {anchor: "".join(unicodedata.normalize("NFKC", anchor).split()) in compact for anchor in case["anchors"]},
        "usable_unit_count": 0,
        "note": "Anchor presence and provider labels are structural smoke checks, not accepted-content accuracy.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", choices=["docling", "paddle"], required=True)
    parser.add_argument("--user-source-dir", type=Path, required=True)
    parser.add_argument("--public-source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cases", default="")
    args = parser.parse_args()
    corpus = json.loads((BASE / "corpus.json").read_text(encoding="utf-8"))
    selected = [case for case in corpus["cases"] if not args.cases or case["id"] in args.cases.split(",")]
    source_paths = {
        key: args.public_source if key == "public_paper" else args.user_source_dir / meta["filename"]
        for key, meta in corpus["sources"].items()
    }
    for key in {case["source"] for case in selected}:
        if sha(source_paths[key]) != corpus["sources"][key]["sha256"]:
            raise ValueError(f"source hash mismatch for {key}")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    save(args.output_dir / "environment.json", {
        "created_at": datetime.now(timezone.utc).isoformat(), "candidate": args.candidate,
        "platform": platform.platform(), "python": sys.version,
        "corpus_sha256": sha(BASE / "corpus.json"),
        "packages": json.loads(subprocess.check_output([sys.executable, "-m", "pip", "list", "--format=json"], text=True)),
        "cases": [case["id"] for case in selected], "local_only": True,
    })
    started = time.perf_counter()
    try:
        probe = DoclingProbe() if args.candidate == "docling" else PaddleProbe()
    except Exception:
        (args.output_dir / "initialization_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    save(args.output_dir / "config.json", probe.config)
    save(args.output_dir / "initialization.json", {"seconds": time.perf_counter()-started})
    summaries = []
    for case in selected:
        directory = args.output_dir / case["id"]
        directory.mkdir()
        print(f"START {args.candidate} {case['id']}", flush=True)
        start = time.perf_counter()
        try:
            normalized = probe.convert(source_paths[case["source"]], case["pages"], directory)
            normalized.update({"schema_version": "structural-probe-v1", "case_id": case["id"],
                               "source_sha256": corpus["sources"][case["source"]]["sha256"]})
            save(directory / "normalized.json", normalized)
            summary = summarize(normalized, case)
            summary.update({"case_id": case["id"], "status": "completed", "seconds": time.perf_counter()-start})
        except Exception:
            (directory / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            summary = {"case_id": case["id"], "status": "failed", "seconds": time.perf_counter()-start}
        save(directory / "summary.json", summary)
        summaries.append(summary)
        save(args.output_dir / "summary.json", summaries)
        print(f"DONE {summary}", flush=True)


if __name__ == "__main__":
    main()
