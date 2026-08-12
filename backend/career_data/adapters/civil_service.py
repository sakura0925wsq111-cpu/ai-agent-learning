"""Adapter for official National Civil Service annual position spreadsheets."""

from pathlib import Path
from typing import Any

from .base import SourceAdapter, read_tabular, resolve_fields


class CivilServiceAdapter(SourceAdapter):
    code = "civil-service"
    publisher = "国家公务员局"
    base_url = "https://www.scs.gov.cn/"
    allowed_domains = ("scs.gov.cn", "gov.cn")
    aliases = {
        "exam_year": ("考试年度", "年份", "exam_year"), "department_code": ("部门代码", "department_code"),
        "department_name": ("部门名称", "department_name"), "employing_department": ("用人司局", "招录机关", "employing_department"),
        "organization_nature": ("机构性质", "organization_nature"),
        "organization_level": ("机构层级", "organization_level"), "position_code": ("职位代码", "招考职位代码", "position_code"),
        "position_name": ("职位名称", "招考职位", "position_name"), "position_description": ("职位简介", "position_description"),
        "position_category": ("职位属性", "职位类别", "position_category"), "recruitment_count": ("招考人数", "计划人数", "recruitment_count"),
        "position_distribution": ("职位分布", "position_distribution"), "exam_category": ("考试类别", "exam_category"),
        "major_requirement_raw": ("专业", "专业要求", "major_requirement_raw"), "education_requirement": ("学历", "education_requirement"),
        "degree_requirement": ("学位", "degree_requirement"), "political_status_requirement": ("政治面貌", "political_status_requirement"),
        "grassroots_experience_requirement": ("基层工作最低年限", "基层工作经历", "grassroots_experience_requirement"),
        "target_group": ("服务基层项目工作经历", "面向人群", "target_group"), "work_location": ("工作地点", "工作地", "work_location"),
        "settlement_location": ("落户地点", "settlement_location"), "interview_ratio": ("面试人员比例", "面试比例", "interview_ratio"),
        "professional_ability_test": ("是否在面试阶段组织专业能力测试", "professional_ability_test"),
        "remarks": ("备注", "remarks"),
    }

    def parse(self, path: Path, **context: Any) -> list[dict[str, Any]]:
        return [resolve_fields(row, self.aliases, {"department_code", "department_name", "position_code", "position_name"}) for row in read_tabular(path)]

    def normalize(self, record: dict[str, Any], **context: Any) -> dict[str, Any]:
        result = dict(record); result["exam_year"] = int(result.get("exam_year") or context.get("year"))
        value = result.get("recruitment_count")
        result["recruitment_count"] = int(value) if value not in (None, "") else None
        return result

    def validate(self, record: dict[str, Any]) -> list[str]:
        errors = []
        for field in ("department_code", "department_name", "position_code", "position_name"):
            if not record.get(field): errors.append(f"{field} is required")
        if not isinstance(record.get("exam_year"), int): errors.append("exam_year must be an integer")
        if record.get("recruitment_count") is not None and record["recruitment_count"] < 0: errors.append("recruitment_count cannot be negative")
        return errors
