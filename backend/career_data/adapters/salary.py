"""Adapter for official MOHRSS enterprise salary survey tables."""

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .base import SourceAdapter, read_tabular, resolve_fields


def _decimal(value: Any) -> float | None:
    if value in (None, "", "—", "-"): return None
    try: return float(Decimal(str(value).replace(",", "").strip()))
    except InvalidOperation as exc: raise ValueError(f"invalid salary number: {value}") from exc


class SalaryAdapter(SourceAdapter):
    code = "salary"
    publisher = "中华人民共和国人力资源和社会保障部"
    base_url = "https://www.mohrss.gov.cn/"
    allowed_domains = ("mohrss.gov.cn",)
    aliases = {
        "survey_year": ("调查年份", "年份", "survey_year"), "occupation_code": ("职业代码", "occupation_code"),
        "occupation_name": ("职业名称", "occupation_name"), "salary_unit": ("工资单位", "单位", "salary_unit"),
        "percentile_10": ("10%分位值", "10分位", "percentile_10"), "percentile_25": ("25%分位值", "25分位", "percentile_25"),
        "percentile_50": ("50%分位值", "中位数", "percentile_50"), "percentile_75": ("75%分位值", "75分位", "percentile_75"),
        "percentile_90": ("90%分位值", "90分位", "percentile_90"), "statistical_scope": ("调查范围", "统计范围", "statistical_scope"),
        "statistical_definition": ("统计口径", "统计定义", "statistical_definition"),
    }

    def parse(self, path: Path, **context: Any) -> list[dict[str, Any]]:
        return [resolve_fields(row, self.aliases, {"occupation_code", "occupation_name", "salary_unit", "statistical_scope", "statistical_definition"}) for row in read_tabular(path)]

    def normalize(self, record: dict[str, Any], **context: Any) -> dict[str, Any]:
        result = dict(record); result["survey_year"] = int(result.get("survey_year") or context.get("year"))
        for field in ("percentile_10", "percentile_25", "percentile_50", "percentile_75", "percentile_90"):
            result[field] = _decimal(result.get(field))
        return result

    def validate(self, record: dict[str, Any]) -> list[str]:
        errors = []
        for field in ("occupation_code", "occupation_name", "salary_unit", "statistical_scope", "statistical_definition"):
            if not record.get(field): errors.append(f"{field} is required")
        values = [record.get(f"percentile_{p}") for p in (10,25,50,75,90)]
        present = [value for value in values if value is not None]
        if len(present) != 5: errors.append("all five salary percentiles are required")
        if len(present) == 5 and present != sorted(present): errors.append("salary percentiles must be non-decreasing")
        return errors
