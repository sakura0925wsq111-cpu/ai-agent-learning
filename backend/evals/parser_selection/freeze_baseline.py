"""Create an immutable, secret-free snapshot of the current Study baseline."""

import hashlib
import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent / "2026-09-04" / "baseline"


def main():
    OUTPUT.mkdir(parents=True, exist_ok=False)
    names = {
        ".gitignore", "requirements.txt", "backend/requirements.txt", "backend/.env.example",
        "backend/core/config.py", "backend/database/session.py", "backend/app/main.py",
        "backend/models/__init__.py", "backend/models/study.py", "backend/schemas/study.py",
        "backend/app/api/v1/study.py", "backend/evals/study_ocr_evaluation.py",
        "backend/evals/study_paragraph_replay.py",
    }
    for pattern in ("backend/services/study*.py", "backend/tests/test_study*.py"):
        names.update(path.relative_to(ROOT).as_posix() for path in ROOT.glob(pattern))
    names.update(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "backend/evals/study_ocr").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
        and path.suffix in {".py", ".json", ".jsonl", ".md"}
    )
    files = []
    with zipfile.ZipFile(OUTPUT / "code_and_evaluations.zip", "x", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(names):
            content = (ROOT / name).read_bytes()
            files.append({"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
            archive.writestr(name, content)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "working_tree_is_dirty": True,
        "archive_sha256": hashlib.sha256((OUTPUT / "code_and_evaluations.zip").read_bytes()).hexdigest(),
        "files": files,
        "exclusions": [".env", "databases", "tokens", "original PDFs", "venv", "model weights"],
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    packages = subprocess.check_output([str(ROOT / "venv/Scripts/python.exe"), "-m", "pip", "list", "--format=json"], text=True)
    (OUTPUT / "packages.json").write_text(packages, encoding="utf-8")
    print(json.dumps({"files": len(files), "archive_sha256": manifest["archive_sha256"]}))


if __name__ == "__main__":
    main()
