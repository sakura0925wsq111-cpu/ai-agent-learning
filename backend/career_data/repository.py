"""Single data-access boundary for ingestion and future read-only consumers."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator

from sqlalchemy import and_, select, text
from sqlalchemy.orm import Session

from .db import CareerDataDatabase

TABLE_CONFIG: dict[str, tuple[str, tuple[str, ...]]] = {
    "postgraduate": ("postgraduate_programs", ("institution_code", "program_code", "admission_year", "study_mode", "special_direction")),
    "undergraduate-majors": ("undergraduate_majors", ("catalog_year", "major_code")),
    "salary": ("salary_benchmarks", ("survey_year", "occupation_code", "statistical_scope")),
    "civil-service": ("civil_service_positions", ("exam_year", "department_code", "position_code")),
    "shandong-civil-service": ("civil_service_positions_v2", ("exam_batch_id", "natural_key")),
    "qut-transfer": ("qut_transfer_policies", ("source_document_id",)),
}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class CareerDataRepository:
    """Repository used by adapters, CLI queries, and later RAG/tool wrappers."""

    def __init__(self, database: CareerDataDatabase) -> None:
        self.database = database

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        session = self.database.session()
        try:
            with session.begin():
                yield session
        finally:
            session.close()

    @staticmethod
    def _rows(session: Session, statement: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return [dict(row) for row in session.execute(text(statement), params or {}).mappings()]

    def get_source(self, code: str, session: Session | None = None) -> dict[str, Any]:
        if session is None:
            with self.transaction() as tx:
                return self.get_source(code, tx)
        row = session.execute(text("SELECT * FROM data_sources WHERE code=:code"), {"code": code}).mappings().first()
        if row is None:
            raise KeyError(f"Unknown data source: {code}")
        return dict(row)

    def list_sources(self) -> list[dict[str, Any]]:
        with self.transaction() as session:
            return self._rows(session, "SELECT * FROM data_sources ORDER BY id")

    def start_run(self, source_code: str, parser_version: str, trigger_type: str) -> int:
        with self.transaction() as session:
            source = self.get_source(source_code, session)
            result = session.execute(text(
                "INSERT INTO ingestion_runs(source_id,status,parser_version,trigger_type) "
                "VALUES (:source_id,'running',:parser_version,:trigger_type)"
            ), {"source_id": source["id"], "parser_version": parser_version, "trigger_type": trigger_type})
            return int(result.lastrowid)

    def finish_run(self, run_id: int, status: str, **counts: Any) -> None:
        allowed = {"records_discovered", "records_inserted", "records_updated", "records_skipped", "error_count", "error_message"}
        values = {key: value for key, value in counts.items() if key in allowed}
        values.update({"id": run_id, "status": status, "finished_at": _now()})
        assignments = ", ".join(f"{key}=:{key}" for key in values if key != "id")
        with self.transaction() as session:
            session.execute(text(f"UPDATE ingestion_runs SET {assignments} WHERE id=:id"), values)

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.transaction() as session:
            return self._rows(session,
                "SELECT r.*,s.code AS source_code FROM ingestion_runs r JOIN data_sources s ON s.id=r.source_id "
                "ORDER BY r.id DESC LIMIT :limit", {"limit": limit})

    def find_document_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        with self.transaction() as session:
            row = session.execute(text("SELECT * FROM source_documents WHERE content_hash=:hash"), {"hash": content_hash}).mappings().first()
            return dict(row) if row else None

    def create_document(self, metadata: dict[str, Any]) -> int:
        columns = tuple(metadata)
        sql = f"INSERT INTO source_documents ({','.join(columns)}) VALUES ({','.join(':'+c for c in columns)})"
        with self.transaction() as session:
            result = session.execute(text(sql), metadata)
            return int(result.lastrowid)

    def update_document_parser_version(self, document_id: int, parser_version: str) -> None:
        with self.transaction() as session:
            session.execute(text(
                "UPDATE source_documents SET parser_version=:parser_version,updated_at=:updated_at WHERE id=:id"
            ), {"id": document_id, "parser_version": parser_version, "updated_at": _now()})

    def add_issue(self, source_code: str, run_id: int | None, *, issue_type: str,
                  severity: str, description: str, document_id: int | None = None,
                  field_name: str | None = None, raw_value: Any = None) -> int:
        with self.transaction() as session:
            source = self.get_source(source_code, session)
            result = session.execute(text(
                "INSERT INTO data_quality_issues(source_id,source_document_id,ingestion_run_id,issue_type,severity,field_name,description,raw_value) "
                "VALUES (:source_id,:document_id,:run_id,:issue_type,:severity,:field_name,:description,:raw_value)"
            ), {"source_id": source["id"], "document_id": document_id, "run_id": run_id,
                "issue_type": issue_type, "severity": severity, "field_name": field_name,
                "description": description, "raw_value": None if raw_value is None else str(raw_value)})
            return int(result.lastrowid)

    def list_quality_issues(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.transaction() as session:
            return self._rows(session,
                "SELECT q.*,s.code AS source_code FROM data_quality_issues q JOIN data_sources s ON s.id=q.source_id "
                "ORDER BY q.id DESC LIMIT :limit", {"limit": limit})

    def persist_records(self, kind: str, records: list[dict[str, Any]], document_id: int,
                        source_url: str) -> tuple[int, int, int]:
        """Insert/update by stable natural key; one transaction prevents half-written batches."""
        table, key_fields = TABLE_CONFIG[kind]
        inserted = updated = skipped = 0
        with self.transaction() as session:
            for source_record in records:
                record = dict(source_record)
                record.update(source_document_id=document_id, source_url=source_url)
                where = " AND ".join(f"{field} IS :{field}" if record.get(field) is None else f"{field}=:{field}" for field in key_fields)
                existing = session.execute(text(f"SELECT * FROM {table} WHERE {where}"), record).mappings().first()
                if existing is None:
                    columns = tuple(record)
                    session.execute(text(
                        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join(':'+c for c in columns)})"
                    ), record)
                    inserted += 1
                    continue
                comparable = {key: value for key, value in record.items() if key not in {"source_document_id", "source_url"}}
                if all(existing.get(key) == value for key, value in comparable.items()):
                    skipped += 1
                    continue
                record["row_id"] = existing["id"]
                record["updated_at"] = _now()
                assignments = ",".join(f"{column}=:{column}" for column in record if column != "row_id")
                session.execute(text(f"UPDATE {table} SET {assignments} WHERE id=:row_id"), record)
                updated += 1
        return inserted, updated, skipped

    def persist_shandong_civil_service(
        self, records: list[dict[str, Any]], document_id: int
    ) -> tuple[int, int, int]:
        """Persist one Shandong workbook and its education-level major requirements."""
        if not records:
            return 0, 0, 0

        first = records[0]
        batch_key = {
            "exam_type": first["exam_type"],
            "exam_year": first["exam_year"],
            "province_code": first["province_code"],
            "batch_code": first["batch_code"],
        }
        batch_values = {
            **batch_key,
            "province_name": first["province_name"],
            "title": first["batch_title"],
            "publisher": first["batch_publisher"],
            "official_entry_url": first["batch_official_entry_url"],
            "coverage_status": first["coverage_status"],
            "coverage_note": first.get("coverage_note"),
            "review_status": first["batch_review_status"],
        }
        batch_metadata_fields = {
            "exam_type", "exam_year", "province_code", "city_code", "batch_code",
            "batch_title", "batch_publisher", "batch_official_entry_url",
            "coverage_status", "coverage_note", "batch_review_status",
            "major_requirements", "_invalid_boolean_fields",
        }

        inserted = updated = skipped = 0
        with self.transaction() as session:
            batch = session.execute(text(
                "SELECT * FROM civil_service_exam_batches WHERE "
                "exam_type=:exam_type AND exam_year=:exam_year "
                "AND province_code=:province_code AND batch_code=:batch_code"
            ), batch_key).mappings().first()
            if batch is None:
                result = session.execute(text(
                    "INSERT INTO civil_service_exam_batches("
                    "exam_type,exam_year,province_code,province_name,batch_code,title,publisher,"
                    "official_entry_url,coverage_status,coverage_note,review_status) VALUES ("
                    ":exam_type,:exam_year,:province_code,:province_name,:batch_code,:title,:publisher,"
                    ":official_entry_url,:coverage_status,:coverage_note,:review_status)"
                ), batch_values)
                batch_id = int(result.lastrowid)
            else:
                batch_id = int(batch["id"])
                session.execute(text(
                    "UPDATE civil_service_exam_batches SET province_name=:province_name,title=:title,"
                    "publisher=:publisher,official_entry_url=:official_entry_url,"
                    "coverage_status=:coverage_status,coverage_note=:coverage_note,"
                    "review_status=CASE WHEN review_status='approved' THEN review_status ELSE :review_status END,"
                    "updated_at=:updated_at WHERE id=:id"
                ), {**batch_values, "updated_at": _now(), "id": batch_id})

            for source_record in records:
                record = {
                    key: value for key, value in source_record.items()
                    if key not in batch_metadata_fields
                }
                majors = list(source_record.get("major_requirements", []))
                record.update(exam_batch_id=batch_id, source_document_id=document_id)
                existing = session.execute(text(
                    "SELECT * FROM civil_service_positions_v2 "
                    "WHERE exam_batch_id=:exam_batch_id AND natural_key=:natural_key"
                ), record).mappings().first()

                if existing is None:
                    columns = tuple(record)
                    result = session.execute(text(
                        f"INSERT INTO civil_service_positions_v2 ({','.join(columns)}) "
                        f"VALUES ({','.join(':'+column for column in columns)})"
                    ), record)
                    position_id = int(result.lastrowid)
                    self._replace_position_majors(session, position_id, majors)
                    inserted += 1
                    continue

                position_id = int(existing["id"])
                existing_majors = [dict(row) for row in session.execute(text(
                    "SELECT education_level,requirement_raw "
                    "FROM civil_service_position_major_requirements "
                    "WHERE position_id=:position_id ORDER BY education_level"
                ), {"position_id": position_id}).mappings()]
                normalized_majors = sorted(majors, key=lambda value: value["education_level"])
                same_position = all(existing.get(key) == value for key, value in record.items())
                if same_position and existing_majors == normalized_majors:
                    skipped += 1
                    continue

                update_values = {**record, "id": position_id, "updated_at": _now()}
                assignments = ",".join(
                    f"{column}=:{column}" for column in record if column not in {"exam_batch_id", "natural_key"}
                )
                session.execute(text(
                    f"UPDATE civil_service_positions_v2 SET {assignments},updated_at=:updated_at WHERE id=:id"
                ), update_values)
                self._replace_position_majors(session, position_id, majors)
                updated += 1
        return inserted, updated, skipped

    @staticmethod
    def _replace_position_majors(session: Session, position_id: int, majors: list[dict[str, str]]) -> None:
        session.execute(text(
            "DELETE FROM civil_service_position_major_requirements WHERE position_id=:position_id"
        ), {"position_id": position_id})
        for major in majors:
            session.execute(text(
                "INSERT INTO civil_service_position_major_requirements("
                "position_id,education_level,requirement_raw) "
                "VALUES (:position_id,:education_level,:requirement_raw)"
            ), {"position_id": position_id, **major})

    def upsert_document_origins(self, document_id: int, origins: list[dict[str, Any]]) -> None:
        with self.transaction() as session:
            for origin in origins:
                existing = session.execute(text(
                    "SELECT id FROM source_document_origins WHERE "
                    "source_document_id=:source_document_id AND origin_type=:origin_type AND url=:url"
                ), {"source_document_id": document_id, **origin}).scalar_one_or_none()
                values = {"source_document_id": document_id, **origin}
                if existing is None:
                    columns = tuple(values)
                    session.execute(text(
                        f"INSERT INTO source_document_origins ({','.join(columns)}) "
                        f"VALUES ({','.join(':'+column for column in columns)})"
                    ), values)
                else:
                    values["id"] = int(existing)
                    session.execute(text(
                        "UPDATE source_document_origins SET publisher=:publisher,"
                        "verification_status=:verification_status,note=:note WHERE id=:id"
                    ), values)

    def get_shandong_civil_service_summary(self, year: int = 2026) -> dict[str, Any]:
        with self.transaction() as session:
            batch = session.execute(text(
                "SELECT * FROM civil_service_exam_batches "
                "WHERE exam_type='provincial' AND exam_year=:year AND province_code='370000' "
                "ORDER BY id DESC LIMIT 1"
            ), {"year": year}).mappings().first()
            if batch is None:
                return {"exam_year": year, "positions": 0, "recruitment_count": 0, "documents": 0}
            totals = session.execute(text(
                "SELECT count(*) AS positions,coalesce(sum(recruitment_count),0) AS recruitment_count,"
                "count(DISTINCT source_document_id) AS documents "
                "FROM civil_service_positions_v2 WHERE exam_batch_id=:batch_id"
            ), {"batch_id": batch["id"]}).mappings().one()
            by_city = self._rows(session,
                "SELECT city_name,count(*) AS positions,sum(recruitment_count) AS recruitment_count "
                "FROM civil_service_positions_v2 WHERE exam_batch_id=:batch_id "
                "GROUP BY city_name ORDER BY city_name", {"batch_id": batch["id"]})
            return {**dict(batch), **dict(totals), "by_city": by_city}

    def search_postgraduate(self, keyword: str | None = None, region: str | None = None,
                            year: int | None = None) -> list[dict[str, Any]]:
        clauses, params = ["1=1"], {}
        if keyword:
            clauses.append("(program_name LIKE :keyword OR institution_name LIKE :keyword OR special_direction LIKE :keyword)")
            params["keyword"] = f"%{keyword}%"
        if region:
            clauses.append("region=:region"); params["region"] = region
        if year:
            clauses.append("admission_year=:year"); params["year"] = year
        with self.transaction() as session:
            return self._rows(session, "SELECT * FROM postgraduate_programs WHERE " + " AND ".join(clauses) + " ORDER BY admission_year DESC,institution_name,program_code", params)

    def search_undergraduate(self, query: str, year: int | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"query": f"%{query}%"}
        year_sql = " AND catalog_year=:year" if year else ""
        if year: params["year"] = year
        with self.transaction() as session:
            return self._rows(session, "SELECT * FROM undergraduate_majors WHERE (major_name LIKE :query OR major_code LIKE :query)" + year_sql + " ORDER BY catalog_year DESC,major_code", params)

    def search_salary(self, query: str, year: int | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"query": f"%{query}%"}
        year_sql = " AND survey_year=:year" if year else ""
        if year: params["year"] = year
        with self.transaction() as session:
            return self._rows(session, "SELECT * FROM salary_benchmarks WHERE (occupation_name LIKE :query OR occupation_code LIKE :query)" + year_sql + " ORDER BY survey_year DESC,occupation_code", params)

    def search_civil_service(self, *, major_text: str | None = None, education: str | None = None,
                             region: str | None = None, year: int | None = None) -> list[dict[str, Any]]:
        clauses, params = ["1=1"], {}
        for field, value in (("major_requirement_raw", major_text), ("education_requirement", education), ("work_location", region)):
            if value:
                clauses.append(f"{field} LIKE :{field}"); params[field] = f"%{value}%"
        if year:
            clauses.append("exam_year=:year"); params["year"] = year
        with self.transaction() as session:
            return self._rows(session, "SELECT * FROM civil_service_positions WHERE " + " AND ".join(clauses) + " ORDER BY exam_year DESC,position_code", params)

    def get_qut_policies(self, current_only: bool = False) -> list[dict[str, Any]]:
        where = "WHERE is_current=1" if current_only else ""
        with self.transaction() as session:
            return self._rows(session, f"SELECT * FROM qut_transfer_policies {where} ORDER BY academic_year DESC,published_at DESC,id DESC")

    def get_source_chain(self, entity_type: str, entity_id: int) -> dict[str, Any] | None:
        table = TABLE_CONFIG[entity_type][0]
        with self.transaction() as session:
            row = session.execute(text(
                f"SELECT r.*,d.title AS document_title,d.content_hash,d.local_path,d.publisher AS document_publisher,"
                "d.retrieved_at,d.review_status AS document_review_status,s.code AS source_code,s.name AS source_name,"
                "s.publisher AS source_publisher,s.base_url FROM " + table + " r "
                "JOIN source_documents d ON d.id=r.source_document_id JOIN data_sources s ON s.id=d.source_id WHERE r.id=:id"
            ), {"id": entity_id}).mappings().first()
            return dict(row) if row else None
