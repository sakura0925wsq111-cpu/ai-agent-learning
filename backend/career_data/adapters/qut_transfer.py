"""Privacy-safe adapter limited to Qingdao University of Technology policies."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .base import AdapterError, SourceAdapter, read_tabular, read_text_document, resolve_fields

RESULT_PATTERNS = ("转专业结果", "转专业名单", "拟录取名单", "录取名单", "学生名单", "结果公示")
STUDENT_ID_RE = re.compile(r"(?<!\d)\d{10,18}(?!\d)")


class QutTransferAdapter(SourceAdapter):
    code = "qut-transfer"
    parser_version = "1.1.2"
    publisher = "青岛理工大学"
    base_url = "https://www.qut.edu.cn/"
    allowed_domains = ("qut.edu.cn",)
    aliases = {
        "title": ("标题", "title"), "policy_type": ("政策类型", "policy_type"),
        "academic_year": ("学年", "适用学年", "academic_year"), "published_at": ("发布日期", "published_at"),
        "valid_from": ("有效期起", "valid_from"), "valid_to": ("有效期止", "valid_to"),
        "applicable_grade": ("适用年级", "applicable_grade"), "applicable_campus": ("适用校区", "applicable_campus"),
        "source_department": ("发布部门", "source_department"), "eligibility_text": ("申请条件", "eligibility_text"),
        "restriction_text": ("限制条件", "restriction_text"), "grade_requirement_text": ("成绩要求", "grade_requirement_text"),
        "process_text": ("办理流程", "process_text"), "assessment_text": ("考核方式", "assessment_text"),
        "quota_text": ("名额", "quota_text"), "timeline_text": ("时间安排", "timeline_text"),
        "full_clean_text": ("政策全文", "全文", "full_clean_text"), "is_current": ("当前有效", "is_current"),
        "review_status": ("审核状态", "review_status"),
    }

    def parse(self, path: Path, **context: Any) -> list[dict[str, Any]]:
        if path.suffix.lower() in {".csv", ".tsv", ".xlsx", ".xlsm"}:
            rows = [resolve_fields(row, self.aliases, {"title", "full_clean_text"}) for row in read_tabular(path)]
        else:
            text = read_text_document(path)
            inferred_title = path.stem
            if path.suffix.lower() in {".html", ".htm"}:
                raw_html = path.read_text(encoding="utf-8", errors="replace")
                match = re.search(r"(?is)<(?:title|h1)[^>]*>(.*?)</(?:title|h1)>", raw_html)
                if match:
                    inferred_title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
            rows = [{"title": context.get("title") or inferred_title, "full_clean_text": text,
                     "academic_year": context.get("year")}]
        for row in rows:
            title = str(row.get("title", ""))
            full_text = str(row.get("full_clean_text", ""))
            if any(pattern in title for pattern in RESULT_PATTERNS):
                raise AdapterError("privacy guard rejected a transfer result/list document")
            if STUDENT_ID_RE.search(full_text):
                raise AdapterError("privacy guard rejected probable student/identity numbers")
        return rows

    @staticmethod
    def _policy_type(title: str) -> str:
        if "接收计划" in title: return "receiving_plan"
        if "补充" in title: return "supplementary_notice"
        if "规定" in title or "办法" in title: return "university_regulation"
        return "annual_notice"

    @staticmethod
    def _section(text: str, start: str, end: str | None = None) -> str | None:
        start_index = text.find(start)
        if start_index < 0:
            return None
        end_index = text.find(end, start_index + len(start)) if end else -1
        return text[start_index:end_index if end_index >= 0 else None].strip() or None

    @staticmethod
    def _regex_section(text: str, start_pattern: str, end_pattern: str) -> str | None:
        start = re.search(start_pattern, text)
        if not start:
            return None
        end = re.search(end_pattern, text[start.end():])
        stop = start.end() + end.start() if end else len(text)
        return text[start.start():stop].strip() or None

    def normalize(self, record: dict[str, Any], **context: Any) -> dict[str, Any]:
        result = dict(record)
        result["policy_type"] = result.get("policy_type") or self._policy_type(str(result.get("title", "")))
        result["academic_year"] = str(result.get("academic_year") or context.get("year") or "") or None
        current = result.get("is_current")
        if isinstance(current, str): current = current.strip().lower() in {"1", "true", "是", "有效"}
        result["is_current"] = current if current in (True, False) else None
        result["review_status"] = result.get("review_status") or ("approved" if result["is_current"] is not None else "needs_review")
        full_text = str(result.get("full_clean_text") or "")
        result["quota_text"] = result.get("quota_text") or self._section(full_text, "一、计划人数", "二、申请条件")
        result["eligibility_text"] = result.get("eligibility_text") or self._section(full_text, "二、申请条件", "三、工作流程")
        if not result.get("restriction_text"):
            result["restriction_text"] = self._regex_section(
                full_text, r"不可转专业的?情形\s*如下\s*[：:]", r"无以上不可转专业情形"
            )
        result["process_text"] = result.get("process_text") or self._section(full_text, "三、工作流程", "四、注意事项")
        result["assessment_text"] = result.get("assessment_text") or self._section(
            result.get("process_text") or "", "2、选拔", "3、录取"
        )
        eligibility_sentences = re.split(r"(?<=[。；;])", result.get("eligibility_text") or "")
        process_sentences = re.split(r"(?<=[。；;])", result.get("process_text") or "")
        if not result.get("grade_requirement_text"):
            grade_sentences = [s.strip() for s in eligibility_sentences if "学分绩点" in s or "不及格课程" in s]
            result["grade_requirement_text"] = " ".join(dict.fromkeys(grade_sentences)) or None
        if not result.get("timeline_text"):
            timeline_sentences = [s.strip() for s in process_sentences if re.search(
                r"\d{1,2}\s*月\s*\d{1,2}\s*日|学年\s*第\s*[12]\s*学期", s
            )]
            result["timeline_text"] = " ".join(dict.fromkeys(timeline_sentences)) or None
        if not result.get("applicable_grade"):
            grades = list(dict.fromkeys(re.findall(r"20\d{2}级", full_text)))
            result["applicable_grade"] = "、".join(grades) or None
        if not result.get("applicable_campus"):
            campuses = [name for name in ("青岛校区", "临沂校区") if name in full_text]
            result["applicable_campus"] = "、".join(campuses) or None
        if not result.get("source_department") and "教务处" in full_text:
            result["source_department"] = "教务处"
        for field in ("published_at", "valid_from", "valid_to"):
            value = result.get(field)
            if value == "": result[field] = None
            elif isinstance(value, str):
                result[field] = datetime.fromisoformat(value) if field == "published_at" else date.fromisoformat(value)
        return result

    def validate(self, record: dict[str, Any]) -> list[str]:
        errors = []
        if not record.get("title"): errors.append("title is required")
        if not record.get("full_clean_text"): errors.append("full_clean_text is required")
        if record.get("policy_type") not in {"university_regulation","annual_notice","receiving_plan","supplementary_notice"}:
            errors.append("invalid policy_type")
        if record.get("review_status") not in {"pending","approved","rejected","needs_review"}:
            errors.append("invalid review_status")
        return errors
