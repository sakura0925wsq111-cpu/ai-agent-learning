"""Audit structural references and frozen-baseline integrity; not OCR accuracy."""

import json
import subprocess
from pathlib import Path

from run_candidates import BASE, save, sha


UNSUPPORTED_TYPES = {"formula", "table", "figure", "caption", "furniture"}


def audit_tree(snapshot):
    nodes = snapshot["blocks"] + snapshot["containers"]
    index = {node["id"]: node for node in nodes}
    duplicates = len(nodes) - len(index)
    dangling = []
    inherited = []
    cycles = []
    for node in nodes:
        references = list(node.get("children", []))
        if node.get("parent_id"):
            references.append(node["parent_id"])
        dangling.extend({"from": node["id"], "to": ref} for ref in references if ref not in index)
    for block in snapshot["blocks"]:
        visited = {block["id"]}
        parent = block.get("parent_id")
        while parent is not None and parent in index:
            if parent in visited:
                cycles.append(block["id"])
                break
            visited.add(parent)
            ancestor = index[parent]
            if ancestor.get("type") in UNSUPPORTED_TYPES:
                inherited.append({"block": block["id"], "ancestor": parent, "type": ancestor["type"]})
                break
            parent = ancestor.get("parent_id")
    return {
        "duplicate_ids": duplicates, "dangling_references": dangling, "parent_cycles": cycles,
        "unsupported_ancestor_relations": inherited,
        "hierarchy_available": bool(snapshot["containers"]),
        "warning": "Valid references are not proof of correct semantic hierarchy or complete Units.",
    }


def main():
    corpus = json.loads((BASE / "corpus.json").read_text(encoding="utf-8"))
    audits = {}
    for candidate in ("docling", "paddle"):
        directory = BASE / f"{candidate}_run1"
        records = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
        audits[candidate] = {
            "completed_cases": sum(item["status"] == "completed" for item in records),
            "measured_conversion_seconds": sum(item["seconds"] for item in records),
            "initialization_seconds": json.loads((directory / "initialization.json").read_text())["seconds"],
            "cases": {},
        }
        for case in corpus["cases"]:
            filename = "normalized_full.json" if candidate == "docling" else "normalized.json"
            snapshot = json.loads((directory / case["id"] / filename).read_text(encoding="utf-8"))
            audits[candidate]["cases"][case["id"]] = audit_tree(snapshot)
    root = Path(__file__).resolve().parents[3]
    frozen = json.loads((BASE / "baseline/manifest.json").read_text(encoding="utf-8"))
    changed = [entry["path"] for entry in frozen["files"] if sha(root / entry["path"]) != entry["sha256"]]
    previous_packages = json.loads((BASE / "baseline/packages.json").read_text(encoding="utf-8"))
    current_packages = json.loads(subprocess.check_output(
        [str(root / "venv/Scripts/python.exe"), "-m", "pip", "list", "--format=json"], text=True
    ))
    package_map = lambda items: {item["name"].lower(): item["version"] for item in items}
    audits["preservation"] = {
        "frozen_file_count": len(frozen["files"]), "changed_baseline_files": changed,
        "main_venv_packages_unchanged": package_map(previous_packages) == package_map(current_packages),
    }
    save(BASE / "structural_audit.json", audits)
    assert not changed, changed
    assert audits["preservation"]["main_venv_packages_unchanged"]
    for candidate in ("docling", "paddle"):
        for result in audits[candidate]["cases"].values():
            assert not result["duplicate_ids"] and not result["dangling_references"] and not result["parent_cycles"]
    print(json.dumps({"preservation": audits["preservation"], "structural_reference_checks": "passed"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
