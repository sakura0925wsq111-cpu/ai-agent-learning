"""Ingestion orchestration: runs, hashes, raw archives, validation, and failures."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .adapters import ADAPTERS
from .adapters.base import AdapterError, SourceAdapter
from .config import DATA_ROOT
from .repository import CareerDataRepository


class IngestionService:
    def __init__(self, repository: CareerDataRepository, raw_root: Path | None = None) -> None:
        self.repository = repository
        self.raw_root = raw_root

    def adapter(self, kind: str) -> SourceAdapter:
        try:
            return ADAPTERS[kind](self.repository, raw_root=self.raw_root)
        except KeyError as exc:
            raise ValueError(f"unknown source kind: {kind}") from exc

    def import_file(self, kind: str, file_path: str | Path, *, source_url: str,
                    title: str | None = None, year: int | None = None,
                    trigger_type: str = "manual_upload", published_at: datetime | None = None,
                    review_status: str | None = None,
                    context: dict[str, Any] | None = None) -> dict[str, Any]:
        adapter = self.adapter(kind)
        adapter.validate_source_url(source_url)
        if review_status not in {None, "pending", "approved", "rejected", "needs_review"}:
            raise ValueError(f"invalid document review status: {review_status}")
        path = Path(file_path).resolve()
        run_id = self.repository.start_run(kind, adapter.parser_version, trigger_type)
        document_id: int | None = None
        document_review_status = review_status or ("needs_review" if kind == "qut-transfer" else "pending")
        adapter_context = {
            **(context or {}), "year": year, "title": title, "source_url": source_url,
        }
        try:
            if not path.is_file():
                raise AdapterError(f"file does not exist: {path}")
            content_hash = adapter.sha256(path)
            existing = self.repository.find_document_by_hash(content_hash)
            if existing and existing["parser_version"] == adapter.parser_version:
                result = {"run_id": run_id, "status": "succeeded", "document_id": existing["id"],
                          "inserted": 0, "updated": 0, "skipped": 1, "duplicate_content": True}
                self.repository.finish_run(run_id, "succeeded", records_discovered=1, records_skipped=1)
                return result
            if existing:
                document_id = int(existing["id"])
                document_review_status = str(existing["review_status"])
                archived = Path(existing["local_path"])
                if not archived.is_absolute():
                    archived = DATA_ROOT / archived
                path = archived
            else:
                archived = adapter.archive_local_file(path, content_hash)
                try:
                    local_path = archived.relative_to(DATA_ROOT).as_posix()
                except ValueError:
                    local_path = archived.as_posix()
                source = self.repository.get_source(kind)
                document_id = self.repository.create_document({
                    "source_id": source["id"], "ingestion_run_id": run_id,
                    "title": title or path.stem, "source_url": source_url, "publisher": adapter.publisher,
                    "document_type": path.suffix.lower().lstrip(".") or "binary", "published_at": published_at,
                    "retrieved_at": datetime.now(UTC).replace(tzinfo=None), "applicable_year": year,
                    "content_hash": content_hash, "local_path": local_path, "mime_type": adapter.mime_type(path),
                    "file_size": path.stat().st_size, "parser_version": adapter.parser_version,
                    "review_status": document_review_status,
                })
            parsed = adapter.parse(path, **adapter_context)
            valid: list[dict[str, Any]] = []
            error_count = 0
            for index, raw_record in enumerate(parsed, start=1):
                try:
                    record = adapter.normalize(raw_record, **adapter_context, row_index=index)
                    errors = adapter.validate(record)
                    if errors:
                        raise AdapterError("; ".join(errors))
                    valid.append(record)
                except (AdapterError, TypeError, ValueError) as exc:
                    error_count += 1
                    self.repository.add_issue(kind, run_id, document_id=document_id,
                        issue_type="record_validation", severity="error", field_name=f"row:{index}",
                        description=str(exc), raw_value=raw_record)
            if not valid:
                raise AdapterError("no valid records parsed")
            inserted, updated, skipped = adapter.persist(valid, document_id, source_url)
            if existing:
                self.repository.update_document_parser_version(document_id, adapter.parser_version)
            needs_review = (
                kind != "qut-transfer" and document_review_status == "needs_review"
            ) or (
                kind == "qut-transfer" and any(row.get("review_status") == "needs_review" for row in valid)
            )
            status = "partial" if error_count else ("requires_manual_review" if needs_review else "succeeded")
            self.repository.finish_run(run_id, status, records_discovered=len(parsed), records_inserted=inserted,
                                       records_updated=updated, records_skipped=skipped, error_count=error_count)
            return {"run_id": run_id, "status": status, "document_id": document_id,
                    "inserted": inserted, "updated": updated, "skipped": skipped,
                    "errors": error_count, "duplicate_content": False}
        except Exception as exc:
            self.repository.add_issue(kind, run_id, document_id=document_id,
                issue_type="ingestion_failure", severity="error", description=str(exc))
            self.repository.finish_run(run_id, "failed", error_count=1, error_message=str(exc))
            return {"run_id": run_id, "status": "failed", "document_id": document_id, "error": str(exc)}

    def import_directory(
        self,
        kind: str,
        directory: str | Path,
        *,
        manifest_path: str | Path,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Validate and import every explicitly listed file in a provenance manifest."""
        adapter = self.adapter(kind)
        root = Path(directory).resolve()
        manifest_file = Path(manifest_path).resolve()
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        if manifest.get("source_code") != kind:
            raise ValueError("manifest source_code does not match requested source")
        entries = manifest.get("documents")
        if not isinstance(entries, list) or not entries:
            raise ValueError("manifest must contain a non-empty documents list")

        dataset_context = dict(manifest.get("dataset") or {})
        results: list[dict[str, Any]] = []
        total_positions = total_recruitment = 0
        failed = 0
        for entry in entries:
            relative_path = Path(str(entry.get("file") or ""))
            path = (root / relative_path).resolve()
            try:
                path.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"manifest file escapes import directory: {relative_path}") from exc

            official_url = str(entry.get("official_page_url") or "")
            adapter.validate_source_url(official_url)
            expected_hash = str(entry.get("sha256") or "").lower()
            context = {
                **dataset_context,
                "city_code": entry.get("city_code"),
                "city_name": entry.get("city_name"),
            }
            item: dict[str, Any] = {"file": relative_path.as_posix()}
            try:
                if not path.is_file():
                    raise AdapterError(f"file does not exist: {path}")
                actual_hash = adapter.sha256(path)
                if not expected_hash or actual_hash != expected_hash:
                    raise AdapterError(
                        f"manifest hash mismatch: expected={expected_hash or 'missing'} actual={actual_hash}"
                    )

                parsed = adapter.parse(path, **context)
                normalized: list[dict[str, Any]] = []
                validation_errors: list[str] = []
                for index, raw_record in enumerate(parsed, start=1):
                    try:
                        row = adapter.normalize(raw_record, **context, row_index=index)
                        errors = adapter.validate(row)
                        if errors:
                            validation_errors.append(f"row {index}: {'; '.join(errors)}")
                        else:
                            normalized.append(row)
                    except (AdapterError, TypeError, ValueError) as exc:
                        validation_errors.append(f"row {index}: {exc}")
                if validation_errors:
                    raise AdapterError("; ".join(validation_errors[:10]))

                positions = len(normalized)
                recruitment_count = sum(row["recruitment_count"] for row in normalized)
                expected_positions = int(entry.get("expected_positions") or 0)
                expected_recruitment = int(entry.get("expected_recruitment_count") or 0)
                if positions != expected_positions or recruitment_count != expected_recruitment:
                    raise AdapterError(
                        "manifest totals mismatch: "
                        f"positions={positions}/{expected_positions}, "
                        f"recruitment={recruitment_count}/{expected_recruitment}"
                    )
                item.update({
                    "status": "validated" if dry_run else "ready",
                    "positions": positions,
                    "recruitment_count": recruitment_count,
                    "sha256": actual_hash,
                })
                total_positions += positions
                total_recruitment += recruitment_count

                if not dry_run:
                    imported = self.import_file(
                        kind,
                        path,
                        source_url=official_url,
                        title=str(entry.get("title") or path.stem),
                        year=int(dataset_context["exam_year"]),
                        trigger_type="manual_upload",
                        review_status=str(entry.get("verification_status") or "needs_review"),
                        context=context,
                    )
                    item.update(imported)
                    if imported.get("document_id"):
                        origins = [{
                            "origin_type": "official_page",
                            "url": official_url,
                            "publisher": str(entry.get("official_publisher") or adapter.publisher),
                            "verification_status": str(entry.get("verification_status") or "needs_review"),
                            "note": "Official information page recorded by the import manifest",
                        }]
                        download_url = str(entry.get("download_url") or "")
                        if download_url:
                            origins.append({
                                "origin_type": str(entry.get("download_origin_type") or "mirror_download"),
                                "url": download_url,
                                "publisher": str(entry.get("download_publisher") or ""),
                                "verification_status": str(entry.get("verification_status") or "needs_review"),
                                "note": "File transfer origin; not treated as the policy authority",
                            })
                        self.repository.upsert_document_origins(int(imported["document_id"]), origins)
                    if imported.get("status") == "failed":
                        failed += 1
            except Exception as exc:
                failed += 1
                item.update({"status": "failed", "error": str(exc)})
            results.append(item)

        return {
            "source": kind,
            "dry_run": dry_run,
            "status": "failed" if failed else ("validated" if dry_run else "requires_manual_review"),
            "files": len(entries),
            "failed_files": failed,
            "positions": total_positions,
            "recruitment_count": total_recruitment,
            "excluded_regions": manifest.get("excluded_regions", []),
            "results": results,
        }

    def ingest(self, kind: str) -> list[dict[str, Any]]:
        adapter = self.adapter(kind)
        discovered = adapter.discover()
        if not discovered:
            run_id = self.repository.start_run(kind, adapter.parser_version, "automatic")
            message = "no stable public batch endpoint configured; use official-file manual import"
            self.repository.add_issue(kind, run_id, issue_type="manual_import_required", severity="info", description=message)
            self.repository.finish_run(run_id, "requires_manual_review", error_count=0, error_message=message)
            return [{"run_id": run_id, "status": "requires_manual_review", "message": message}]
        results = []
        for remote in discovered:
            try:
                local = adapter.download(remote)
                results.append(self.import_file(kind, local, source_url=remote.url, title=remote.title,
                    year=remote.applicable_year, published_at=remote.published_at, trigger_type="automatic"))
            except Exception as exc:
                run_id = self.repository.start_run(kind, adapter.parser_version, "automatic")
                self.repository.add_issue(kind, run_id, issue_type="download_failure", severity="error", description=str(exc))
                self.repository.finish_run(run_id, "failed", error_count=1, error_message=str(exc))
                results.append({"run_id": run_id, "status": "failed", "error": str(exc)})
        return results

    def ingest_all(self) -> dict[str, list[dict[str, Any]]]:
        results: dict[str, list[dict[str, Any]]] = {}
        for kind, adapter_class in ADAPTERS.items():
            try:
                results[kind] = self.ingest(kind)
            except Exception as exc:
                run_id = self.repository.start_run(kind, adapter_class.parser_version, "automatic")
                self.repository.add_issue(kind, run_id, issue_type="source_isolation_failure",
                                          severity="error", description=str(exc))
                self.repository.finish_run(run_id, "failed", error_count=1, error_message=str(exc))
                results[kind] = [{"run_id": run_id, "status": "failed", "error": str(exc)}]
        return results
