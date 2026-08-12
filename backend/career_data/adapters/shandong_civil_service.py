"""Adapter for Shandong provincial civil-service position spreadsheets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import SourceAdapter, read_tabular, resolve_fields


def _text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _optional_bool(value: Any) -> tuple[bool | None, bool]:
    """Return (normalized value, recognized) for the yes/no columns."""
    cleaned = _text(value)
    if cleaned is None:
        return None, True
    compact = cleaned.replace(" ", "")
    if compact in {"是", "需要", "有"}:
        return True, True
    if compact.startswith("是，") or compact.startswith("是,"):
        return True, True
    if compact in {"否", "不需要", "无"}:
        return False, True
    return None, False


class ShandongCivilServiceAdapter(SourceAdapter):
    code = "shandong-civil-service"
    parser_version = "1.0.0"
    publisher = "中共山东省委组织部"
    base_url = "https://gwy.sdrsks.org.cn/"
    allowed_domains = (
        "sdrsks.org.cn", "shandong.gov.cn", "dtdjzx.gov.cn", "qingdao.gov.cn",
        "dongyingdj.gov.cn", "yantai.gov.cn", "jiningdq.cn", "dtts.gov.cn",
        "wfzzb.gov.cn", "rzzzb.gov.cn", "bzzzb.gov.cn", "lczgw.gov.cn",
        "hezedj.gov.cn",
    )
    aliases = {
        "recruitment_authority": ("招录机关",),
        "employing_unit": ("用人单位",),
        "position_code": ("职位代码",),
        "position_name": ("职位名称",),
        "position_nature": ("职位性质",),
        "position_category": ("职位类别",),
        "position_attribute": ("职位属性",),
        "exam_category": ("公共科目笔试类别", "公共科目考试类别"),
        "position_description": ("职位简介",),
        "recruitment_count": ("招录计划",),
        "target_group": ("招录对象",),
        "education_requirement": ("学历要求",),
        "degree_requirement": ("学位要求",),
        "associate_major_requirement": ("大学专科专业要求",),
        "bachelor_major_requirement": ("大学本科专业要求",),
        "postgraduate_major_requirement": ("研究生专业要求",),
        "gender_requirement": ("性别要求",),
        "household_requirement": ("户籍或生源地要求",),
        "political_status_requirement": ("政治面貌",),
        "grassroots_experience_requirement": ("基层工作最低年限",),
        "professional_exam_required_raw": ("是否需要专业科目考试",),
        "professional_test_required_raw": ("是否在面试阶段组织专业能力测试",),
        "differential_inspection_raw": ("是否差额考察",),
        "psychological_test_required_raw": ("是否组织心理素质测评",),
        "special_medical_exam_required_raw": ("是否执行特殊体检标准",),
        "work_location": ("工作地点",),
        "remarks": ("备注",),
        "information_website": ("单位信息发布网站",),
        "consultation_phone_1": ("咨询电话1", "咨询电话"),
        "consultation_phone_2": ("咨询电话2",),
        "consultation_phone_3": ("咨询电话3",),
    }
    required_fields = {
        "recruitment_authority", "employing_unit", "position_code", "position_name",
        "recruitment_count", "education_requirement", "work_location",
    }

    def parse(self, path: Path, **context: Any) -> list[dict[str, Any]]:
        return read_tabular(path)

    def normalize(self, record: dict[str, Any], **context: Any) -> dict[str, Any]:
        resolved = resolve_fields(record, self.aliases, self.required_fields)
        try:
            recruitment_count = int(float(resolved["recruitment_count"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("recruitment_count must be an integer") from exc

        city_code = str(context.get("city_code") or "").strip()
        city_name = str(context.get("city_name") or "").strip()
        position_code = str(resolved["position_code"]).strip()
        flags: dict[str, bool | None] = {}
        invalid_boolean_fields: list[str] = []
        for target, raw_field in (
            ("professional_exam_required", "professional_exam_required_raw"),
            ("professional_test_required", "professional_test_required_raw"),
            ("differential_inspection", "differential_inspection_raw"),
            ("psychological_test_required", "psychological_test_required_raw"),
            ("special_medical_exam_required", "special_medical_exam_required_raw"),
        ):
            flags[target], recognized = _optional_bool(resolved.get(raw_field))
            if not recognized:
                invalid_boolean_fields.append(raw_field)

        phones = [
            phone for phone in (
                _text(resolved.get("consultation_phone_1")),
                _text(resolved.get("consultation_phone_2")),
                _text(resolved.get("consultation_phone_3")),
            ) if phone
        ]
        phones = list(dict.fromkeys(phones))

        major_requirements = []
        for level, field in (
            ("associate", "associate_major_requirement"),
            ("bachelor", "bachelor_major_requirement"),
            ("postgraduate", "postgraduate_major_requirement"),
        ):
            requirement = _text(resolved.get(field))
            if requirement:
                major_requirements.append({"education_level": level, "requirement_raw": requirement})

        normalized = {
            "exam_type": "provincial",
            "exam_year": int(context.get("year") or context.get("exam_year")),
            "province_code": str(context.get("province_code") or "370000"),
            "province_name": str(context.get("province_name") or "山东省"),
            "city_code": city_code,
            "city_name": city_name,
            "batch_code": str(context.get("batch_code") or "initial"),
            "batch_title": str(context.get("batch_title") or "山东省公务员考试录用职位表"),
            "batch_publisher": str(context.get("batch_publisher") or self.publisher),
            "batch_official_entry_url": str(context.get("batch_official_entry_url") or self.base_url),
            "coverage_status": str(context.get("coverage_status") or "partial"),
            "coverage_note": _text(context.get("coverage_note")),
            "batch_review_status": str(context.get("batch_review_status") or "needs_review"),
            "natural_key": f"{city_code}:{position_code}",
            "recruitment_authority": _text(resolved["recruitment_authority"]),
            "employing_unit": _text(resolved["employing_unit"]),
            "department_code": None,
            "position_code": position_code,
            "position_name": _text(resolved["position_name"]),
            "position_nature": _text(resolved.get("position_nature")),
            "position_category": _text(resolved.get("position_category")),
            "position_attribute": _text(resolved.get("position_attribute")),
            "exam_category": _text(resolved.get("exam_category")),
            "position_description": _text(resolved.get("position_description")),
            "recruitment_count": recruitment_count,
            "target_group": _text(resolved.get("target_group")),
            "education_requirement": _text(resolved["education_requirement"]),
            "degree_requirement": _text(resolved.get("degree_requirement")),
            "gender_requirement": _text(resolved.get("gender_requirement")),
            "household_requirement": _text(resolved.get("household_requirement")),
            "political_status_requirement": _text(resolved.get("political_status_requirement")),
            "grassroots_experience_requirement": _text(resolved.get("grassroots_experience_requirement")),
            **flags,
            "differential_inspection_detail": _text(resolved.get("differential_inspection_raw")),
            "work_location": _text(resolved["work_location"]),
            "remarks": _text(resolved.get("remarks")),
            "information_website": _text(resolved.get("information_website")),
            "consultation_phones_json": json.dumps(phones, ensure_ascii=False),
            "source_row_number": int(context.get("row_index") or 0),
            "raw_payload_json": json.dumps(record, ensure_ascii=False, default=str),
            "major_requirements": major_requirements,
            "_invalid_boolean_fields": invalid_boolean_fields,
        }
        return normalized

    def validate(self, record: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for field in (
            "exam_year", "city_code", "city_name", "natural_key", "recruitment_authority",
            "employing_unit", "position_code", "position_name", "education_requirement",
            "work_location", "source_row_number",
        ):
            if record.get(field) in (None, "", 0):
                errors.append(f"{field} is required")
        if record.get("recruitment_count", 0) <= 0:
            errors.append("recruitment_count must be positive")
        if not record.get("major_requirements"):
            errors.append("at least one education-level major requirement is required")
        if record.get("_invalid_boolean_fields"):
            errors.append("unrecognized yes/no values: " + ", ".join(record["_invalid_boolean_fields"]))
        return errors

    def persist(self, records: list[dict[str, Any]], document_id: int, source_url: str) -> tuple[int, int, int]:
        return self.repository.persist_shandong_civil_service(records, document_id)
