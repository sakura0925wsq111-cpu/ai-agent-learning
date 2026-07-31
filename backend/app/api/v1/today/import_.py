# -*- coding: utf-8 -*-
"""PDF & Excel Import API — deterministic parsers for university教务系统 files.

PDF course schedule: table extraction + regex, zero LLM.
Excel exam schedule: column-mapped extraction, zero LLM.
"""

from __future__ import annotations

import io, json, re, uuid
from datetime import date as dt_date
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session
from loguru import logger

from database.session import get_db
from schemas.response import APIResponse
from schemas.today import ImportConfirmRequest
from models.today import Course, Exam
from services.llm_service import get_llm_service

router = APIRouter()
_preview_store: dict[str, dict[str, Any]] = {}

WEEKDAY_KW = ["星期一","星期二","星期三","星期四","星期五","星期六","星期日"]
_EXAM_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\((\d{2}:\d{2})-(\d{2}:\d{2})\)")

# ═══════════════════════════════════════════════════════════════
#  COURSE PDF PARSER (deterministic, zero LLM)
# ═══════════════════════════════════════════════════════════════

_PERIOD_RE = re.compile(r"\((?P<ps>\d+)-(?P<pe>\d+)节\)\s*(?P<weeks>[\d\-]+周(?:\([双单]\))?)")


def _parse_cell(cell_text: str, weekday: int) -> list[dict[str, Any]]:
    text = " ".join(cell_text.split())
    courses: list[dict[str, Any]] = []

    for pm in re.finditer(_PERIOD_RE, text):
        ps = int(pm.group("ps"))
        pe = int(pm.group("pe"))
        weeks = pm.group("weeks").strip()

        before = text[:pm.start()]
        name = ""
        last_marker = None
        for m in re.finditer(r"[★○●◇◆]", before):
            last_marker = m
        if last_marker:
            after_marker = before[last_marker.end():].strip()
            if after_marker:
                name = after_marker
            else:
                name_before = before[:last_marker.start()].strip()
                parts = name_before.split()
                name = parts[-1] if parts else ""
        name = re.sub(r"[★○●◇◆]", "", name).strip()

        after = text[pm.end():]
        loc_m = re.search(r"/场地:\s*([^/\n]+)", after)
        tch_m = re.search(r"/教师:\s*([^/\n]+)", after)

        courses.append({
            "name": name or "(未命名课程)",
            "teacher": tch_m.group(1).strip() if tch_m else None,
            "location": loc_m.group(1).strip() if loc_m else None,
            "schedule": [{"weekday": weekday, "start": ps, "end": pe, "weeks": weeks}],
        })
    return courses


def _extract_courses_from_pdf(file_bytes: bytes) -> list[dict[str, Any]]:
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("pdfplumber required: pip install pdfplumber")

    all_courses: list[dict[str, Any]] = []
    saved_col_map: dict[int, int] | None = None

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2: continue
                col_map: dict[int, int] = {}
                for row in table:
                    if not row: continue
                    for ci, cell in enumerate(row):
                        if cell:
                            for kw, wd in zip(WEEKDAY_KW, range(1, 8)):
                                if kw in str(cell):
                                    col_map[ci] = wd
                    if col_map:
                        saved_col_map = dict(col_map)
                        break
                if not col_map:
                    col_map = saved_col_map or {}
                if not col_map: continue
                for row in table:
                    if not row: continue
                    for col_idx, weekday in col_map.items():
                        ct = str(row[col_idx] or "").strip() if col_idx < len(row) else ""
                        if not ct or ct == "None" or len(ct) < 8: continue
                        if any(kw in ct and len(ct) < 12 for kw in WEEKDAY_KW): continue
                        all_courses.extend(_parse_cell(ct, weekday))
    return all_courses


# ═══════════════════════════════════════════════════════════════
#  EXAM EXCEL PARSER (deterministic, zero LLM)
# ═══════════════════════════════════════════════════════════════

# Column name mappings (Chinese header -> English key)
_EXAM_COL_MAP = {
    "课程名称": "subject",
    "考试日期": "exam_date_raw",
    "考试地点": "location",
}


def _extract_exams_from_xlsx(file_bytes: bytes) -> list[dict[str, Any]]:
    """Parse exam schedule from university教务系统 Excel format.

    Expected columns: 课程名称, 考试日期(YYYY-MM-DD(HH:MM-HH:MM)), 考试地点
    """
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("openpyxl required: pip install openpyxl")

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), )
    ws = wb.active
    if not ws:
        raise RuntimeError("Excel file has no active sheet")

    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return []

    # Find column indices from header row
    header = rows[0]
    col_idx: dict[str, int] = {}
    for ci, cell in enumerate(header):
        if cell:
            key = _EXAM_COL_MAP.get(str(cell).strip())
            if key:
                col_idx[key] = ci

    if "subject" not in col_idx or "exam_date_raw" not in col_idx:
        raise RuntimeError(
            "Excel must contain columns: 课程名称, 考试日期. "
            f"Found: {list(col_idx.keys())}"
        )

    exams: list[dict[str, Any]] = []
    for row in rows[1:]:
        if not row: continue

        subject = str(row[col_idx["subject"]] or "").strip()
        date_raw = str(row[col_idx["exam_date_raw"]] or "").strip()
        location = str(row[col_idx.get("location", -1)] or "").strip() if "location" in col_idx else None

        if not subject or not date_raw:
            continue

        # Parse date: "2026-07-15(10:10-12:00)"
        dm = _EXAM_DATE_RE.search(date_raw)
        if not dm:
            exams.append({
                "subject": subject,
                "exam_date": None,
                "start_time": None,
                "end_time": None,
                "location": location or None,
                "source": "excel_import",
            })
            continue

        exams.append({
            "subject": subject,
            "exam_date": dm.group(1),
            "start_time": dm.group(2),
            "end_time": dm.group(3),
            "location": location or None,
            "source": "excel_import",
        })

    wb.close()
    return exams


# ═══════════════════════════════════════════════════════════════
#  EXAM PDF PARSER (LLM fallback for unstructured exam PDFs)
# ═══════════════════════════════════════════════════════════════

def _extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for p in pdf.pages:
                t = p.extract_text()
                if t: parts.append(t)
        return "\n".join(parts)
    except ImportError:
        pass
    try:
        from PyPDF2 import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(file_bytes)).pages)
    except ImportError:
        raise RuntimeError("No PDF library.")


def _parse_exams_llm(raw_text: str, llm) -> list[dict[str, Any]]:
    prompt = (
        "Extract all exams. Output JSON array.\n"
        'Each: {"subject":"Name","exam_date":"2026-07-15",'
        '"start_time":"09:00","end_time":"11:00","location":"Room"}\n'
        "Output ONLY JSON array."
    )
    try:
        resp = llm.chat(user_message="Parse:\n"+raw_text[:4000],
                        system_prompt=prompt, temperature=0.1, max_tokens=2000)
        m = re.search(r"\[.*\]", resp, re.DOTALL)
        return json.loads(m.group()) if m else []
    except Exception as exc:
        logger.error("Exam LLM parse failed: {}", exc)
        return []


# ═══════════════════════════════════════════════════════════════
#  API ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@router.post("/import", response_model=APIResponse[dict])
async def import_pdf(
    file: UploadFile = File(...),
    user_id: str = Query(..., description="User ID"),
    import_type: str = Query("course", description="course or exam"),
    db: Session = Depends(get_db),
):
    """Import course/exam data from PDF files."""
    if file.content_type and "pdf" not in file.content_type:
        return APIResponse.error(code=400, message="Only PDF files supported for this endpoint. Use /import/excel for Excel.")

    file_bytes = await file.read()

    if import_type == "course":
        try:
            items = _extract_courses_from_pdf(file_bytes)
        except Exception as exc:
            logger.error("Course PDF failed: {}", exc)
            return APIResponse.error(code=400, message=str(exc))
    else:
        raw = _extract_text_from_pdf(file_bytes)
        if not raw.strip():
            return APIResponse.error(code=400, message="PDF empty")
        items = _parse_exams_llm(raw, get_llm_service())

    if not items:
        return APIResponse.error(code=422, message="No items found in PDF")

    return _store_preview(user_id, import_type, items)


@router.post("/import/excel", response_model=APIResponse[dict])
async def import_excel(
    file: UploadFile = File(...),
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db),
):
    """Import exam data from Excel (.xlsx) files.

    Supports the university教务系统 exam schedule format.
    Columns: 课程名称, 考试日期, 考试地点
    """
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        return APIResponse.error(code=400, message="Only .xlsx / .xls files supported")

    file_bytes = await file.read()

    try:
        items = _extract_exams_from_xlsx(file_bytes)
    except Exception as exc:
        logger.error("Excel exam import failed: {}", exc)
        return APIResponse.error(code=400, message=str(exc))

    if not items:
        return APIResponse.error(code=422, message="No exam records found in Excel file")

    return _store_preview(user_id, "exam", items)


@router.post("/import/confirm", response_model=APIResponse[dict])
def confirm_import(payload: ImportConfirmRequest, db: Session = Depends(get_db)):
    """Confirm a previewed import and save items to database."""
    preview = _preview_store.pop(payload.import_id, None)
    if preview is None:
        return APIResponse.error(code=404, message="Preview not found or already confirmed")

    user_id, itype, items = preview["user_id"], preview["import_type"], preview["items"]
    saved = 0

    if itype == "course":
        for item in items:
            try:
                db.add(Course(user_id=user_id, name=item.get("name", ""),
                    teacher=item.get("teacher"), location=item.get("location"),
                    schedule_json=json.dumps(item.get("schedule", []), ensure_ascii=False),
                    source="pdf_import"))
                saved += 1
            except Exception as exc:
                logger.warning("Course save fail: {}", exc)
    else:  # exam
        for item in items:
            try:
                db.add(Exam(user_id=user_id, subject=item.get("subject", ""),
                    exam_date=item.get("exam_date"), start_time=item.get("start_time"),
                    end_time=item.get("end_time"), location=item.get("location"),
                    source=item.get("source", "excel_import")))
                saved += 1
            except Exception as exc:
                logger.warning("Exam save fail: {}", exc)

    db.commit()
    logger.info("Import confirmed: {} {}/{}", itype, saved, len(items))
    return APIResponse.ok(data={"import_id": payload.import_id, "saved_count": saved})


def _store_preview(user_id: str, import_type: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Store parsed items as preview, return standard response."""
    import_id = str(uuid.uuid4())
    _preview_store[import_id] = {"user_id": user_id, "import_type": import_type, "items": items}
    logger.info("Import preview: {} {} items (id={})", import_type, len(items), import_id)
    return APIResponse.ok(data={
        "import_id": import_id, "import_type": import_type,
        "total": len(items), "items": items,
    })
