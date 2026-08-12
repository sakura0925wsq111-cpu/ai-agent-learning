# -*- coding: utf-8 -*-
"""PDF & Excel Import API -- deterministic parsers for university files.

PDF course schedule: ★-marker based cell splitting + regex extraction, zero LLM.
Excel exam schedule: flexible column-mapped extraction, zero LLM.
"""

from __future__ import annotations

import io, json, re
from datetime import date as dt_date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session
from loguru import logger

from database.session import get_db
from schemas.response import APIResponse
from schemas.today import ImportConfirmRequest
from core.config import settings
from models.today import Course, Exam, ImportPreview
from services.llm_service import get_llm_service
from utils.auth import get_current_user_id, require_user_access

router = APIRouter()

@router.get("/import/preview", response_model=APIResponse[dict])
def get_import_preview(
    import_id: str = Query(..., description="Import preview ID"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Get import preview data by import_id."""
    preview = db.get(ImportPreview, import_id)
    if preview is None:
        return APIResponse.error(code=404, message="导入预览不存在或已过期")
    require_user_access(preview.user_id, current_user_id)
    if _is_preview_expired(preview):
        return APIResponse.error(code=410, message="导入预览已过期，请重新上传")
    items = json.loads(preview.items_json)
    return APIResponse.ok(data={
        "import_id": import_id,
        "import_type": preview.import_type,
        "status": preview.status,
        "total": len(items),
        "items": items,
    })


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _is_preview_expired(preview: ImportPreview) -> bool:
    return _as_utc(preview.expires_at) <= datetime.now(timezone.utc)


async def _read_upload(
    file: UploadFile,
    *,
    suffixes: tuple[str, ...],
    label: str,
    magic: tuple[bytes, ...],
) -> bytes:
    filename = (file.filename or "").lower()
    if not filename.endswith(suffixes):
        raise ValueError(f"仅支持 {label} 文件")
    content = await file.read(settings.upload_max_bytes + 1)
    if not content:
        raise ValueError("上传文件为空")
    if len(content) > settings.upload_max_bytes:
        raise ValueError(f"文件不能超过 {settings.upload_max_bytes // (1024 * 1024)} MB")
    if magic and not any(content.startswith(signature) for signature in magic):
        raise ValueError(f"文件内容不是有效的 {label} 格式")
    return content

WEEKDAY_KW = ["星期一","星期二","星期三","星期四","星期五","星期六","星期日"]
_EXAM_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\((\d{2}:\d{2})-(\d{2}:\d{2})\)")

# Semester mapping
_SEMESTER_PATTERN = re.compile(
    r"(\d{4})-(\d{4})学年第?(\d)学期"
)

def _infer_semester_start(pdf_text: str) -> dt_date | None:
    m = _SEMESTER_PATTERN.search(pdf_text)
    if not m:
        return None
    year1 = int(m.group(1))
    semester = int(m.group(3))
    if semester == 1:
        return dt_date(year1, 9, 1)
    else:
        return dt_date(int(m.group(2)), 2, 15)


# Week parsing utilities

_WEEKS_RE = re.compile(r"^(\d+)-(\d+)周(?:\(([单双])\))?$")


def _parse_weeks(weeks_str: str) -> dict[str, Any]:
    m = _WEEKS_RE.match((weeks_str or "").strip())
    if not m:
        return {"start": 1, "end": 20, "parity": None, "raw": weeks_str}
    parity = None
    if m.group(3) == "单":
        parity = "odd"
    elif m.group(3) == "双":
        parity = "even"
    return {
        "start": int(m.group(1)),
        "end": int(m.group(2)),
        "parity": parity,
        "raw": weeks_str.strip(),
    }


def _is_course_active_in_week(
    weeks_parsed: dict[str, Any], current_week: int
) -> bool:
    if current_week < weeks_parsed["start"]:
        return False
    if current_week > weeks_parsed["end"]:
        return False
    if weeks_parsed["parity"] == "odd" and current_week % 2 == 0:
        return False
    if weeks_parsed["parity"] == "even" and current_week % 2 != 0:
        return False
    return True


def _get_current_week(semester_start: dt_date) -> int:
    delta = dt_date.today() - semester_start
    if delta.days < 0:
        return 0
    return delta.days // 7 + 1


def _get_week_for_date(semester_start: dt_date, target: dt_date) -> int:
    delta = target - semester_start
    if delta.days < 0:
        return 0
    return delta.days // 7 + 1


# Course PDF parser (★-marker based)

_PERIOD_WEEKS_RE = re.compile(
    r"\((\d+)-(\d+)节\)\s*([\d\-]+周(?:\([单双]\))?)"
)
_LOCATION_RE = re.compile(r"/场地:\s*([^/\n]+)")
_TEACHER_RE  = re.compile(r"/教师:\s*([^/\n]+)")


def _parse_cell(cell_text: str, weekday: int) -> list[dict[str, Any]]:
    text = cell_text.strip()
    if not text:
        return []

    star_positions = [m.start() for m in re.finditer(r"★", text)]
    if not star_positions:
        return []

    courses: list[dict[str, Any]] = []

    for i, pos in enumerate(star_positions):
        prev_boundary = star_positions[i - 1] + 1 if i > 0 else 0
        name_block = text[prev_boundary:pos]
        name_lines = [l for l in name_block.split("\n") if l.strip()]
        name = name_lines[-1].strip() if name_lines else ""
        name = re.sub(r"[★○●◇◆]", "", name).strip()
        if not name:
            continue

        next_boundary = (
            star_positions[i + 1] if i + 1 < len(star_positions) else len(text)
        )
        after_block = text[pos + 1 : next_boundary]

        pw = _PERIOD_WEEKS_RE.search(after_block)
        if not pw:
            continue
        ps = int(pw.group(1))
        pe = int(pw.group(2))
        weeks_raw = pw.group(3).strip()

        loc_m = _LOCATION_RE.search(after_block)
        tch_m = _TEACHER_RE.search(after_block)

        weeks_parsed = _parse_weeks(weeks_raw)

        courses.append({
            "name": name,
            "teacher": tch_m.group(1).strip() if tch_m else None,
            "location": loc_m.group(1).strip() if loc_m else None,
            "schedule": [{
                "weekday": weekday,
                "start": ps,
                "end": pe,
                "weeks": weeks_raw,
                "weeks_parsed": weeks_parsed,
            }],
        })

    return courses


def _extract_courses_from_pdf(
    file_bytes: bytes,
) -> tuple[list[dict[str, Any]], dt_date | None]:
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("pdfplumber required: pip install pdfplumber")

    all_courses: list[dict[str, Any]] = []
    saved_col_map: dict[int, int] | None = None
    semester_start: dt_date | None = None
    all_text_parts: list[str] = []

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            all_text_parts.append(page_text)

            if semester_start is None and page_text:
                semester_start = _infer_semester_start(page_text)

            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue

                col_map: dict[int, int] = {}
                for row in table:
                    if not row:
                        continue
                    for ci, cell in enumerate(row):
                        if cell and isinstance(cell, str):
                            for kw, wd in zip(WEEKDAY_KW, range(1, 8)):
                                if kw in cell:
                                    col_map[ci] = wd
                    if col_map:
                        saved_col_map = dict(col_map)
                        break
                if not col_map:
                    col_map = saved_col_map or {}
                if not col_map:
                    continue

                for row in table:
                    if not row:
                        continue
                    for col_idx, weekday in col_map.items():
                        ct = (
                            str(row[col_idx] or "").strip()
                            if col_idx < len(row)
                            else ""
                        )
                        if not ct or ct == "None" or "★" not in ct:
                            continue
                        if any(kw in ct and len(ct) < 12 for kw in WEEKDAY_KW):
                            continue
                        all_courses.extend(_parse_cell(ct, weekday))

    if semester_start is None:
        full_text = "\n".join(all_text_parts)
        semester_start = _infer_semester_start(full_text)

    return all_courses, semester_start


# Exam Excel parser

_EXAM_COL_MAP: dict[str, str] = {
    "课程名称": "subject",
    "科目": "subject",
    "课程": "subject",
    "考试课程": "subject",
    "考试科目": "subject",
    "考试日期": "exam_date_raw",
    "日期": "exam_date_raw",
    "考试时间": "exam_date_raw",
    "时间": "exam_date_raw",
    "考试地点": "location",
    "地点": "location",
    "考场": "location",
    "场地简称": "location",
}

_DATE_TIME_RE_PATTERNS = [
    re.compile(r"(\d{4}-\d{2}-\d{2})\((\d{2}:\d{2})-(\d{2}:\d{2})\)"),
    re.compile(r"(\d{4}/\d{2}/\d{2})\s*(\d{2}:\d{2})-(\d{2}:\d{2})"),
    re.compile(r"(\d{4}年\d{2}月\d{2}日)\s*(\d{2}:\d{2})-(\d{2}:\d{2})"),
    re.compile(r"(\d{4}-\d{2}-\d{2})"),
    re.compile(r"(\d{4}/\d{2}/\d{2})"),
]


def _extract_exams_from_xlsx(file_bytes: bytes) -> list[dict[str, Any]]:
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("openpyxl required: pip install openpyxl")

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
    ws = wb.active
    if not ws:
        raise RuntimeError("Excel file has no active sheet")

    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        wb.close()
        return []

    header = rows[0]
    col_idx: dict[str, int] = {}
    for ci, cell in enumerate(header):
        cell_str = str(cell).strip() if cell else ""
        key = _EXAM_COL_MAP.get(cell_str)
        if key and key not in col_idx:
            col_idx[key] = ci

    if "subject" not in col_idx or "exam_date_raw" not in col_idx:
        wb.close()
        return []

    exams: list[dict[str, Any]] = []
    subj_col = col_idx["subject"]
    date_col = col_idx["exam_date_raw"]
    loc_col = col_idx.get("location")

    for row in rows[1:]:
        if not row:
            continue

        subject = str(row[subj_col] or "").strip() if subj_col < len(row) else ""
        date_raw = str(row[date_col] or "").strip() if date_col < len(row) else ""
        location = (
            str(row[loc_col] or "").strip()
            if loc_col is not None and loc_col < len(row)
            else None
        )

        if not subject or not date_raw:
            continue

        matched = False
        for pat in _DATE_TIME_RE_PATTERNS:
            dm = pat.search(date_raw)
            if dm:
                groups = dm.groups()
                try:
                    date_str = groups[0].replace("年", "-").replace("月", "-").replace("日", "")
                    parsed_date = dt_date.fromisoformat(date_str)
                except (ValueError, IndexError):
                    parsed_date = None
                if len(groups) >= 3:
                    exams.append({
                        "subject": subject,
                        "exam_date": parsed_date,
                        "start_time": groups[1],
                        "end_time": groups[2],
                        "location": location or None,
                        "source": "excel_import",
                    })
                elif len(groups) >= 1:
                    exams.append({
                        "subject": subject,
                        "exam_date": parsed_date,
                        "start_time": None,
                        "end_time": None,
                        "location": location or None,
                        "source": "excel_import",
                    })
                matched = True
                break

        if not matched:
            logger.warning("Could not parse an exam date value")

    wb.close()
    return exams


# Exam PDF parser (LLM fallback)

def _extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for p in pdf.pages:
                t = p.extract_text()
                if t:
                    parts.append(t)
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
        resp = llm.chat(
            user_message="Parse:\n" + raw_text[:4000],
            system_prompt=prompt,
            temperature=0.1,
            max_tokens=2000,
        )
        m = re.search(r"\[.*\]", resp, re.DOTALL)
        if m:
            items = json.loads(m.group())
            for item in items:
                if isinstance(item.get("exam_date"), str):
                    try:
                        item["exam_date"] = dt_date.fromisoformat(item["exam_date"])
                    except (ValueError, TypeError):
                        pass
            return items
        return []
    except Exception as exc:
        logger.error("Exam LLM parse failed: {}", exc)
        return []


# API endpoints

@router.post("/import", response_model=APIResponse[dict])
async def import_pdf(
    file: UploadFile = File(...),
    user_id: str = Query(..., description="User ID"),
    import_type: str = Query("course", description="course or exam"),
    semester_start: str | None = Query(
        None,
        description="Semester start date YYYY-MM-DD. Overrides auto-detection.",
    ),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    require_user_access(user_id, current_user_id)
    try:
        file_bytes = await _read_upload(
            file, suffixes=(".pdf",), label="PDF", magic=(b"%PDF-",)
        )
    except ValueError as exc:
        return APIResponse.error(code=400, message=str(exc))
    resolved_semester: dt_date | None = None

    if import_type == "course":
        try:
            items, auto_semester = _extract_courses_from_pdf(file_bytes)
        except Exception as exc:
            logger.error("Course PDF failed: {}", exc)
            return APIResponse.error(code=400, message=str(exc))

        if semester_start:
            try:
                resolved_semester = dt_date.fromisoformat(semester_start)
            except ValueError:
                return APIResponse.error(code=400, message="Invalid semester_start format, use YYYY-MM-DD")
        elif auto_semester:
            resolved_semester = auto_semester

        if resolved_semester:
            logger.info("Semester start resolved: {}", resolved_semester.isoformat())
    else:
        raw = _extract_text_from_pdf(file_bytes)
        if not raw.strip():
            return APIResponse.error(code=400, message="PDF empty")
        items = _parse_exams_llm(raw, get_llm_service())

    if not items:
        return APIResponse.error(code=422, message="No items found in PDF")

    return _store_preview(db, user_id, import_type, items, resolved_semester)


@router.post("/import/excel", response_model=APIResponse[dict])
async def import_excel(
    file: UploadFile = File(...),
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    require_user_access(user_id, current_user_id)
    try:
        file_bytes = await _read_upload(
            file, suffixes=(".xlsx",), label=".xlsx", magic=(b"PK\x03\x04",)
        )
    except ValueError as exc:
        return APIResponse.error(code=400, message=str(exc))

    try:
        items = _extract_exams_from_xlsx(file_bytes)
    except Exception as exc:
        logger.error("Excel exam import failed: {}", exc)
        return APIResponse.error(code=400, message=str(exc))

    if not items:
        return APIResponse.error(code=422, message="No exam records found in Excel file")

    return _store_preview(db, user_id, "exam", items)


@router.post("/import/confirm", response_model=APIResponse[dict])
def confirm_import(
    payload: ImportConfirmRequest,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    preview = db.get(ImportPreview, payload.import_id)
    if preview is None:
        return APIResponse.error(code=404, message="导入预览不存在")
    require_user_access(preview.user_id, current_user_id)
    if preview.status == "confirmed" and preview.result_json:
        return APIResponse.ok(data=json.loads(preview.result_json), message="该导入已确认")
    if preview.status != "pending":
        return APIResponse.error(code=409, message="导入正在处理，请勿重复提交")
    if _is_preview_expired(preview):
        preview.status = "expired"
        db.commit()
        return APIResponse.error(code=410, message="导入预览已过期，请重新上传")

    claimed = db.query(ImportPreview).filter(
        ImportPreview.id == payload.import_id,
        ImportPreview.status == "pending",
    ).update({ImportPreview.status: "processing"}, synchronize_session=False)
    db.commit()
    if claimed != 1:
        latest = db.get(ImportPreview, payload.import_id)
        if latest and latest.status == "confirmed" and latest.result_json:
            return APIResponse.ok(data=json.loads(latest.result_json), message="该导入已确认")
        return APIResponse.error(code=409, message="导入正在处理，请勿重复提交")
    db.refresh(preview)
    user_id, itype, items = preview.user_id, preview.import_type, json.loads(preview.items_json)
    if payload.selected_indexes is not None:
        selected = sorted(set(payload.selected_indexes))
        if any(index < 0 or index >= len(items) for index in selected):
            preview.status = "pending"
            db.commit()
            return APIResponse.error(code=400, message="预览选择项无效，请刷新后重试")
        items = [items[index] for index in selected]
    if not items:
        preview.status = "pending"
        db.commit()
        return APIResponse.error(code=400, message="请至少选择一项导入")
    saved = 0
    try:
        if itype == "course":
            # An import replaces only rows created by prior imports for this user.
            db.query(Course).filter(
                Course.user_id == user_id,
                Course.source == "pdf_import",
            ).delete()
            semester_start_val = (
                dt_date.fromisoformat(preview.semester_start)
                if preview.semester_start else None
            )
            for item in items:
                db.add(
                    Course(
                        user_id=user_id,
                        name=item.get("name", ""),
                        teacher=item.get("teacher"),
                        location=item.get("location"),
                        schedule_json=json.dumps(
                            item.get("schedule", []), ensure_ascii=False
                        ),
                        semester_start=semester_start_val,
                        source="pdf_import",
                    )
                )
                saved += 1
        else:
            db.query(Exam).filter(
                Exam.user_id == user_id,
                Exam.source == "excel_import",
            ).delete()
            for item in items:
                exam_date = item.get("exam_date")
                if isinstance(exam_date, str):
                    try:
                        exam_date = dt_date.fromisoformat(exam_date)
                    except (ValueError, TypeError):
                        exam_date = None
                db.add(
                    Exam(
                        user_id=user_id,
                        subject=item.get("subject", ""),
                        exam_date=exam_date,
                        start_time=item.get("start_time"),
                        end_time=item.get("end_time"),
                        location=item.get("location"),
                        source=item.get("source", "excel_import"),
                    )
                )
                saved += 1

        result: dict[str, Any] = {"import_id": payload.import_id, "saved_count": saved}
        if preview.semester_start:
            result["semester_start"] = preview.semester_start
        preview.status = "confirmed"
        preview.confirmed_at = datetime.now(timezone.utc)
        preview.result_json = json.dumps(result, ensure_ascii=False)
        db.commit()
    except Exception:
        db.rollback()
        stored = db.get(ImportPreview, payload.import_id)
        if stored and stored.status == "processing":
            stored.status = "pending"
            db.commit()
        logger.exception("Import confirmation failed: id={}", payload.import_id)
        return APIResponse.error(code=500, message="导入保存失败，请稍后重试")
    logger.info("Import confirmed: {} {}/{}", itype, saved, len(items))
    return APIResponse.ok(data=result)


def _store_preview(
    db: Session,
    user_id: str,
    import_type: str,
    items: list[dict[str, Any]],
    semester_start: dt_date | None = None,
) -> dict[str, Any]:
    preview = ImportPreview(
        user_id=user_id,
        import_type=import_type,
        items_json=json.dumps(items, ensure_ascii=False, default=str),
        semester_start=semester_start.isoformat() if semester_start else None,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.import_preview_ttl_seconds),
    )
    db.add(preview)
    db.commit()
    db.refresh(preview)
    import_id = preview.id
    logger.info("Import preview: {} {} items (id={})", import_type, len(items), import_id)
    return APIResponse.ok(data={
        "import_id": import_id, "import_type": import_type,
        "total": len(items),
        "items": items,
        "semester_start": semester_start.isoformat() if semester_start else None,
    })
