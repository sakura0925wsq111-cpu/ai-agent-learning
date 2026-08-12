"""Parser for Ministry of Education undergraduate catalogue PDF/tabular exports."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import RemoteDocument, SourceAdapter, read_tabular, read_text_document, resolve_fields


class UndergraduateMajorsAdapter(SourceAdapter):
    code = "undergraduate-majors"
    publisher = "中华人民共和国教育部"
    base_url = "https://www.moe.gov.cn/"
    allowed_domains = ("moe.gov.cn",)
    LATEST_URL = "https://www.moe.gov.cn/srcsite/A08/moe_1034/s3882/202604/W020260427440749576927.pdf"
    aliases = {
        "catalog_year": ("目录年份", "年份", "catalog_year"),
        "discipline_code": ("学科门类代码", "门类代码", "discipline_code"),
        "discipline_name": ("学科门类", "门类名称", "discipline_name"),
        "major_category_code": ("专业类代码", "major_category_code"),
        "major_category_name": ("专业类名称", "专业类", "major_category_name"),
        "major_code": ("专业代码", "major_code"),
        "major_name": ("专业名称", "major_name"),
        "degree_category": ("授予学位门类", "学位门类", "degree_category"),
    }

    def discover(self) -> list[RemoteDocument]:
        return [RemoteDocument(self.LATEST_URL, "普通高等学校本科专业目录（2026年）", 2026,
                               datetime(2026, 4, 7))]

    def parse(self, path: Path, **context: Any) -> list[dict[str, Any]]:
        if path.suffix.lower() != ".pdf":
            return [resolve_fields(row, self.aliases,
                    {"discipline_code", "discipline_name", "major_category_code", "major_category_name", "major_code", "major_name"})
                    for row in read_tabular(path)]
        text = read_text_document(path)
        discipline_code = discipline_name = category_code = category_name = None
        records: list[dict[str, Any]] = []
        for raw_line in text.splitlines():
            line = " ".join(raw_line.split())
            discipline = re.match(r"^(\d{2})\s+学科门类[：:]\s*(.+)$", line)
            if discipline:
                discipline_code, discipline_name = discipline.groups()
                continue
            category = re.match(r"^(\d{4})\s+(.+类)$", line)
            if category:
                category_code, category_name = category.groups()
                continue
            # Foreign-language codes exceeded six digits after 0502099; the
            # Ministry's 2026 catalogue contains 0502100T..0502107TK.
            major = re.match(r"^(\d{6,7}[TK]{0,2})\s+(.+)$", line)
            if not major or not all((discipline_code, discipline_name, category_code, category_name)):
                continue
            code, name_with_note = major.groups()
            name = re.sub(r"（注[：:].*?）$", "", name_with_note).strip()
            note = name_with_note[len(name):].strip("（）") or None
            degree = note.replace("注：", "") if note else discipline_name
            records.append({
                "catalog_year": context.get("year"), "discipline_code": discipline_code,
                "discipline_name": discipline_name, "major_category_code": category_code,
                "major_category_name": category_name, "major_code": code, "major_name": name,
                "degree_category": degree,
            })
        if not records:
            from .base import StructureChangedError
            raise StructureChangedError("no six-digit major rows found; PDF layout may have changed")
        return records

    def normalize(self, record: dict[str, Any], **context: Any) -> dict[str, Any]:
        result = dict(record)
        result["catalog_year"] = int(result.get("catalog_year") or context.get("year"))
        result["major_code"] = str(result["major_code"]).strip().upper()
        result["is_special"] = "T" in result["major_code"]
        result["is_state_controlled"] = "K" in result["major_code"]
        result["is_basic"] = not result["is_special"]
        return result

    def validate(self, record: dict[str, Any]) -> list[str]:
        errors = []
        if not re.fullmatch(r"\d{6,7}[TK]{0,2}", record.get("major_code", "")): errors.append("invalid major_code")
        if not isinstance(record.get("catalog_year"), int): errors.append("catalog_year must be an integer")
        for field in ("discipline_code", "discipline_name", "major_category_code", "major_category_name", "major_name"):
            if not record.get(field): errors.append(f"{field} is required")
        return errors
