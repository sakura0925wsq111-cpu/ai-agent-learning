"""Offline tests for the independent career-data minimum closed loop."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy import text

from career_data.adapters import ADAPTERS
from career_data.adapters.base import RemoteDocument
from career_data.db import CareerDataDatabase
from career_data.repository import CareerDataRepository
from career_data.service import IngestionService

FIXTURES = Path(__file__).parent / "fixtures" / "career_data"
OFFICIAL_MOE_PDF = Path(__file__).parents[1] / "data" / "career_data" / "raw" / "undergraduate-majors" / "moe-undergraduate-catalog-2026.pdf"
OFFICIAL_QUT_DIR = Path(__file__).parents[1] / "data" / "career_data" / "raw" / "qut-transfer"
OFFICIAL_CIVIL_XLS = Path(__file__).parents[1] / "data" / "career_data" / "raw" / "civil-service" / "2670bae1df1dd07a3a3c79b9db46a11e3bb15a6c9c249e6af98bfd0b61ce3aaf.xls"
SHANDONG_ROOT = Path(__file__).parents[1] / "data" / "career_data" / "raw" / "shandong-civil-service" / "2026"
SHANDONG_MANIFEST = SHANDONG_ROOT / "manifest.json"
URLS = {
    "postgraduate": "https://yz.chsi.com.cn/kyzx/fixture",
    "undergraduate-majors": "https://www.moe.gov.cn/fixture.pdf",
    "salary": "https://www.mohrss.gov.cn/fixture.xlsx",
    "civil-service": "https://www.scs.gov.cn/fixture.xlsx",
    "qut-transfer": "https://jwc.qut.edu.cn/fixture.html",
}


@pytest.fixture()
def store(tmp_path: Path) -> tuple[CareerDataDatabase, CareerDataRepository, IngestionService]:
    database = CareerDataDatabase(f"sqlite:///{(tmp_path / 'career.db').as_posix()}")
    assert database.migrate() == [
        "0001_initial.sql", "0002_civil_service_official_fields.sql",
        "0003_civil_service_natural_key.sql", "0004_shandong_civil_service_schema.sql",
    ]
    assert database.migrate() == []
    repository = CareerDataRepository(database)
    return database, repository, IngestionService(repository, raw_root=tmp_path / "raw")


@pytest.mark.parametrize(("kind", "fixture", "year"), [
    ("postgraduate", "postgraduate.csv", 2026),
    ("undergraduate-majors", "undergraduate.csv", 2026),
    ("salary", "salary.csv", 2025),
    ("civil-service", "civil_service.csv", 2026),
    ("qut-transfer", "qut_policy.html", 2026),
])
def test_each_adapter_parses_normal_local_fixture(store, kind: str, fixture: str, year: int) -> None:
    _, _, service = store
    result = service.import_file(kind, FIXTURES / fixture, source_url=URLS[kind], year=year,
                                 title="青岛理工大学本科生转专业管理规定" if kind == "qut-transfer" else None,
                                 trigger_type="local_fixture")
    assert result["status"] in {"succeeded", "requires_manual_review"}
    assert result["inserted"] == 1


def test_official_moe_2026_pdf_parses_all_883_majors(store) -> None:
    _, repository, _ = store
    adapter = ADAPTERS["undergraduate-majors"](repository)
    parsed = adapter.parse(OFFICIAL_MOE_PDF, year=2026)
    normalized = [adapter.normalize(row, year=2026) for row in parsed]
    assert len(normalized) == 883
    assert all(not adapter.validate(row) for row in normalized)
    assert {row["major_code"] for row in normalized if len(row["major_code"].rstrip("TK")) == 7} == {
        "0502100T", "0502101T", "0502102T", "0502103T",
        "0502104TK", "0502105T", "0502106TK", "0502107TK",
    }


@pytest.mark.parametrize("year", [2024, 2025, 2026])
def test_official_qut_notices_extract_policy_sections_without_personal_data(store, year: int) -> None:
    _, repository, _ = store
    adapter = ADAPTERS["qut-transfer"](repository)
    row = adapter.normalize(adapter.parse(
        OFFICIAL_QUT_DIR / f"qut-transfer-notice-{year}.html",
        year=year, title=f"关于开展{year}年本科生转专业工作的通知",
    )[0], year=year)
    for field in ("eligibility_text", "restriction_text", "grade_requirement_text", "process_text",
                  "assessment_text", "quota_text", "timeline_text"):
        assert row[field]
    assert row["review_status"] == "needs_review" and row["is_current"] is None
    assert row["source_department"] == "教务处"


def test_official_2026_civil_service_xls_parses_every_sheet(store) -> None:
    _, repository, _ = store
    adapter = ADAPTERS["civil-service"](repository)
    normalized = [adapter.normalize(row, year=2026) for row in adapter.parse(OFFICIAL_CIVIL_XLS)]
    assert len(normalized) == 20_714
    assert sum(row["recruitment_count"] for row in normalized) == 38_119
    assert len({(row["department_code"], row["position_code"]) for row in normalized}) == 20_714
    assert all(not adapter.validate(row) for row in normalized)


def test_shandong_manifest_dry_run_validates_all_supported_files(store) -> None:
    _, _, service = store
    result = service.import_directory(
        "shandong-civil-service", SHANDONG_ROOT,
        manifest_path=SHANDONG_MANIFEST, dry_run=True,
    )
    assert result["status"] == "validated"
    assert result["files"] == 16 and result["failed_files"] == 0
    assert result["positions"] == 5_842
    assert result["recruitment_count"] == 7_685
    assert result["excluded_regions"] == ["德州市"]


def test_shandong_single_file_import_is_traceable_and_idempotent(store, tmp_path: Path) -> None:
    database, repository, service = store
    manifest = json.loads(SHANDONG_MANIFEST.read_text(encoding="utf-8"))
    manifest["documents"] = [
        entry for entry in manifest["documents"] if entry["city_name"] == "青岛市"
    ]
    manifest_path = tmp_path / "qingdao-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    first = service.import_directory(
        "shandong-civil-service", SHANDONG_ROOT,
        manifest_path=manifest_path,
    )
    assert first["status"] == "requires_manual_review" and first["failed_files"] == 0
    summary = repository.get_shandong_civil_service_summary(2026)
    assert summary["positions"] == 505
    assert summary["recruitment_count"] == 734
    assert summary["documents"] == 1
    assert summary["coverage_status"] == "partial"
    with database.session() as session:
        assert session.execute(text("SELECT count(*) FROM source_document_origins")).scalar_one() == 2
        assert session.execute(text(
            "SELECT count(*) FROM civil_service_position_major_requirements"
        )).scalar_one() >= 505
        assert session.execute(text(
            "SELECT review_status FROM source_documents"
        )).scalar_one() == "needs_review"
        assert session.execute(text(
            "SELECT count(*) FROM civil_service_positions_v2 WHERE raw_payload_json <> ''"
        )).scalar_one() == 505

    second = service.import_directory(
        "shandong-civil-service", SHANDONG_ROOT,
        manifest_path=manifest_path,
    )
    assert second["results"][0]["duplicate_content"] is True
    assert repository.get_shandong_civil_service_summary(2026)["positions"] == 505


def test_empty_file_and_missing_headers_are_recorded(store, tmp_path: Path) -> None:
    _, repository, service = store
    empty = service.import_file("salary", FIXTURES / "empty.csv", source_url=URLS["salary"], year=2025,
                                trigger_type="local_fixture")
    malformed = tmp_path / "changed.csv"
    malformed.write_text("unknown,new-header\n1,2\n", encoding="utf-8")
    changed = service.import_file("postgraduate", malformed, source_url=URLS["postgraduate"], year=2026,
                                  trigger_type="local_fixture")
    assert empty["status"] == changed["status"] == "failed"
    assert len(repository.list_quality_issues()) == 2


def test_duplicate_file_hash_is_idempotent(store) -> None:
    _, repository, service = store
    first = service.import_file("undergraduate-majors", FIXTURES / "undergraduate.csv",
                                source_url=URLS["undergraduate-majors"], year=2026, trigger_type="local_fixture")
    second = service.import_file("undergraduate-majors", FIXTURES / "undergraduate.csv",
                                 source_url=URLS["undergraduate-majors"], year=2026, trigger_type="local_fixture")
    assert first["inserted"] == 1
    assert second["duplicate_content"] is True and second["skipped"] == 1
    assert len(repository.search_undergraduate("080901")) == 1


def test_automatic_download_reuses_archived_hash(store, tmp_path: Path) -> None:
    _, repository, service = store
    source = FIXTURES / "undergraduate.csv"
    first = service.import_file("undergraduate-majors", source,
        source_url=URLS["undergraduate-majors"], year=2026, trigger_type="local_fixture")
    archived = Path(repository.get_source_chain("undergraduate-majors", 1)["local_path"])
    class FakeDownloader:
        def get(self, url: str) -> bytes:
            return source.read_bytes()
    adapter = ADAPTERS["undergraduate-majors"](
        repository, downloader=FakeDownloader(), raw_root=tmp_path / "raw"
    )
    downloaded = adapter.download(RemoteDocument(URLS["undergraduate-majors"], "fixture", 2026))
    assert downloaded.name == archived.name
    assert len(list((tmp_path / "raw" / "undergraduate-majors").iterdir())) == 1


def test_new_parser_version_reprocesses_same_document_without_duplication(store) -> None:
    database, repository, service = store
    first = service.import_file("qut-transfer", FIXTURES / "qut_policy.html",
        source_url=URLS["qut-transfer"], title="青岛理工大学本科生转专业管理规定",
        year=2026, trigger_type="local_fixture")
    with database.engine.begin() as connection:
        connection.execute(text("UPDATE source_documents SET parser_version='0.9.0' WHERE id=:id"),
                           {"id": first["document_id"]})
    second = service.import_file("qut-transfer", FIXTURES / "qut_policy.html",
        source_url=URLS["qut-transfer"], title="青岛理工大学本科生转专业管理规定",
        year=2026, trigger_type="local_fixture")
    assert second["duplicate_content"] is False
    with database.session() as session:
        assert session.execute(text("SELECT count(*) FROM source_documents")).scalar_one() == 1
        assert session.execute(text("SELECT parser_version FROM source_documents")).scalar_one() == "1.1.2"


def test_annual_increment_preserves_old_version(store) -> None:
    _, repository, service = store
    for year, name in ((2025, "undergraduate_2025.csv"), (2026, "undergraduate.csv")):
        result = service.import_file("undergraduate-majors", FIXTURES / name,
            source_url=URLS["undergraduate-majors"], year=year, trigger_type="local_fixture")
        assert result["inserted"] == 1
    rows = repository.search_undergraduate("080901")
    assert [row["catalog_year"] for row in rows] == [2026, 2025]


def test_civil_position_code_is_scoped_by_department(store, tmp_path: Path) -> None:
    database, _, service = store
    path = tmp_path / "same-position-code.csv"
    path.write_text(
        "考试年度,部门代码,部门名称,职位代码,职位名称,招考人数,专业,学历,工作地点\n"
        "2026,001,部门甲,P001,职位甲,1,计算机类,本科及以上,北京市\n"
        "2026,002,部门乙,P001,职位乙,1,法学类,本科及以上,上海市\n",
        encoding="utf-8",
    )
    result = service.import_file("civil-service", path, source_url=URLS["civil-service"],
                                 year=2026, trigger_type="local_fixture")
    assert result["inserted"] == 2
    with database.session() as session:
        assert session.execute(text("SELECT count(*) FROM civil_service_positions")).scalar_one() == 2


def test_bad_type_causes_partial_import_without_losing_good_row(store) -> None:
    _, repository, service = store
    result = service.import_file("salary", FIXTURES / "salary_partial.csv", source_url=URLS["salary"],
                                 year=2025, trigger_type="local_fixture")
    assert result["status"] == "partial" and result["inserted"] == 1 and result["errors"] == 1
    assert len(repository.search_salary("软件工程")) == 1


def test_xlsx_header_change_detection(store, tmp_path: Path) -> None:
    _, _, service = store
    path = tmp_path / "changed.xlsx"
    workbook = Workbook(); sheet = workbook.active
    sheet.append(["不认识的列", "另一个列"]); sheet.append(["a", "b"]); workbook.save(path)
    result = service.import_file("civil-service", path, source_url=URLS["civil-service"], year=2026,
                                 trigger_type="local_fixture")
    assert result["status"] == "failed" and "header changed" in result["error"]


def test_repository_batch_transaction_rolls_back(store) -> None:
    database, repository, service = store
    imported = service.import_file("undergraduate-majors", FIXTURES / "undergraduate.csv",
        source_url=URLS["undergraduate-majors"], year=2026, trigger_type="local_fixture")
    document_id = imported["document_id"]
    good = {"catalog_year": 2027, "discipline_code": "08", "discipline_name": "工学",
            "major_category_code": "0809", "major_category_name": "计算机类", "major_code": "080901",
            "major_name": "计算机科学与技术", "is_basic": True, "is_special": False,
            "is_state_controlled": False, "degree_category": "工学"}
    bad = dict(good, major_code="080902", nonexistent_column="boom")
    with pytest.raises(Exception):
        repository.persist_records("undergraduate-majors", [good, bad], document_id, URLS["undergraduate-majors"])
    with database.session() as session:
        assert session.execute(text("SELECT count(*) FROM undergraduate_majors WHERE catalog_year=2027")).scalar_one() == 0


def test_qut_versions_coexist_unknown_status_and_privacy_guard(store) -> None:
    _, repository, service = store
    current = service.import_file("qut-transfer", FIXTURES / "qut_policy_current.csv", source_url=URLS["qut-transfer"],
                                  year=2026, trigger_type="local_fixture")
    historical = service.import_file("qut-transfer", FIXTURES / "qut_policy.html", source_url=URLS["qut-transfer"],
                                     title="青岛理工大学2025年转专业通知", year=2025, trigger_type="local_fixture")
    rejected = service.import_file("qut-transfer", FIXTURES / "qut_result.html", source_url=URLS["qut-transfer"],
                                   year=2026, trigger_type="local_fixture")
    assert current["status"] == "succeeded"
    assert historical["status"] == "requires_manual_review"
    assert rejected["status"] == "failed" and "privacy guard" in rejected["error"]
    policies = repository.get_qut_policies()
    assert len(policies) == 2 and {row["review_status"] for row in policies} == {"approved", "needs_review"}


def test_queries_and_complete_source_chain(store) -> None:
    _, repository, service = store
    imports = {
        "postgraduate": ("postgraduate.csv", 2026), "undergraduate-majors": ("undergraduate.csv", 2026),
        "salary": ("salary.csv", 2025), "civil-service": ("civil_service.csv", 2026),
    }
    for kind, (name, year) in imports.items():
        service.import_file(kind, FIXTURES / name, source_url=URLS[kind], year=year, trigger_type="local_fixture")
    assert repository.search_postgraduate("计算机", "北京", 2026)
    major = repository.search_undergraduate("080901", 2026)[0]
    assert repository.search_salary("2-02", 2025)
    assert repository.search_civil_service(major_text="计算机", education="本科", region="青岛", year=2026)
    chain = repository.get_source_chain("undergraduate-majors", major["id"])
    assert chain and chain["content_hash"] and chain["local_path"] and chain["source_publisher"] == "中华人民共和国教育部"


def test_non_official_qut_url_is_rejected_before_run(store) -> None:
    _, repository, service = store
    with pytest.raises(ValueError, match="non-official"):
        service.import_file("qut-transfer", FIXTURES / "qut_policy.html",
                            source_url="https://example.com/policy.html", year=2026)
    assert repository.list_runs() == []


def test_all_adapters_expose_six_stage_interface(store) -> None:
    _, repository, _ = store
    for adapter_class in ADAPTERS.values():
        adapter = adapter_class(repository)
        for method in ("discover", "download", "parse", "normalize", "validate", "persist"):
            assert callable(getattr(adapter, method))


def test_ingest_all_isolates_one_source_failure(store, monkeypatch: pytest.MonkeyPatch) -> None:
    _, repository, service = store
    def fake_ingest(kind: str):
        if kind == "salary":
            raise RuntimeError("simulated source outage")
        return [{"status": "requires_manual_review"}]
    monkeypatch.setattr(service, "ingest", fake_ingest)
    results = service.ingest_all()
    assert results["salary"][0]["status"] == "failed"
    assert all(results[kind][0]["status"] == "requires_manual_review" for kind in ADAPTERS if kind != "salary")
    assert repository.list_runs()[0]["source_code"] == "salary"
