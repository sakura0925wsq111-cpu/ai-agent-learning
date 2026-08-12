"""Low-frequency/manual adapter for the official YZ postgraduate catalogue."""

from pathlib import Path
from typing import Any

from .base import SourceAdapter, read_tabular, resolve_fields


class PostgraduateAdapter(SourceAdapter):
    code = "postgraduate"
    publisher = "中国研究生招生信息网"
    base_url = "https://yz.chsi.com.cn/"
    allowed_domains = ("yz.chsi.com.cn",)
    aliases = {
        "institution_code": ("招生单位代码", "院校代码", "institution_code"),
        "institution_name": ("招生单位名称", "院校名称", "institution_name"),
        "region": ("所在地", "地区", "region"),
        "discipline_category_code": ("门类代码", "学科门类代码", "discipline_category_code"),
        "discipline_category_name": ("门类名称", "学科门类", "discipline_category_name"),
        "first_level_discipline_code": ("一级学科代码", "first_level_discipline_code"),
        "first_level_discipline_name": ("一级学科名称", "一级学科", "first_level_discipline_name"),
        "program_code": ("专业代码", "program_code"),
        "program_name": ("专业名称", "program_name"),
        "degree_type": ("学位类型", "专业类型", "degree_type"),
        "study_mode": ("学习方式", "study_mode"),
        "special_direction": ("研究方向", "方向", "special_direction"),
        "admission_year": ("招生年度", "年份", "admission_year"),
    }

    def parse(self, path: Path, **context: Any) -> list[dict[str, Any]]:
        return [resolve_fields(row, self.aliases, {"institution_name", "program_code", "program_name"})
                for row in read_tabular(path)]

    def normalize(self, record: dict[str, Any], **context: Any) -> dict[str, Any]:
        result = dict(record)
        result["admission_year"] = int(result.get("admission_year") or context.get("year"))
        for key in result:
            if isinstance(result[key], str):
                result[key] = " ".join(result[key].split()) or None
        return result

    def validate(self, record: dict[str, Any]) -> list[str]:
        errors = []
        if not record.get("institution_name"): errors.append("institution_name is required")
        if not record.get("program_code"): errors.append("program_code is required")
        if not record.get("program_name"): errors.append("program_name is required")
        if not isinstance(record.get("admission_year"), int): errors.append("admission_year must be an integer")
        return errors
