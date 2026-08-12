"""CLI: python -m career_data ..."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from decimal import Decimal
from typing import Any

from .adapters import ADAPTERS
from .db import CareerDataDatabase
from .repository import CareerDataRepository
from .service import IngestionService


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, Decimal)): return str(value)
    raise TypeError(type(value).__name__)


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=_json_default))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="career-data", description="Independent official career-data store")
    parser.add_argument("--database-url", help="Override CAREER_DATA_DATABASE_URL")
    groups = parser.add_subparsers(dest="group", required=True)
    db = groups.add_parser("db"); db.add_subparsers(dest="action", required=True).add_parser("init")
    sources = groups.add_parser("sources"); sources.add_subparsers(dest="action", required=True).add_parser("list")
    ingest = groups.add_parser("ingest"); ingest.add_argument("source", choices=[*ADAPTERS, "all"])
    imported = groups.add_parser("import")
    imported.add_argument("source", choices=ADAPTERS); imported.add_argument("file")
    imported.add_argument("--source-url", required=True, help="Exact official page or attachment URL")
    imported.add_argument("--title"); imported.add_argument("--year", type=int)
    imported.add_argument("--published-at", type=datetime.fromisoformat, help="Official publication date/time (ISO 8601)")
    imported_directory = groups.add_parser("import-directory")
    imported_directory.add_argument("source", choices=["shandong-civil-service"])
    imported_directory.add_argument("directory")
    imported_directory.add_argument("--manifest", required=True)
    imported_directory.add_argument("--dry-run", action="store_true")
    runs = groups.add_parser("runs"); runs.add_subparsers(dest="action", required=True).add_parser("list")
    quality = groups.add_parser("quality"); quality.add_subparsers(dest="action", required=True).add_parser("list")
    query = groups.add_parser("query"); query.add_argument("entity", choices=[*ADAPTERS, "source-chain"])
    query.add_argument("--text", default=""); query.add_argument("--year", type=int); query.add_argument("--region")
    query.add_argument("--education"); query.add_argument("--current-only", action="store_true")
    query.add_argument("--entity-type", choices=ADAPTERS); query.add_argument("--id", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    database = CareerDataDatabase(args.database_url)
    migrated = database.migrate()
    repository = CareerDataRepository(database)
    service = IngestionService(repository)
    if args.group == "db": _print({"database_url": database.database_url, "migrations_applied": migrated})
    elif args.group == "sources": _print(repository.list_sources())
    elif args.group == "runs": _print(repository.list_runs())
    elif args.group == "quality": _print(repository.list_quality_issues())
    elif args.group == "ingest": _print(service.ingest_all() if args.source == "all" else service.ingest(args.source))
    elif args.group == "import": _print(service.import_file(args.source, args.file, source_url=args.source_url,
                                                              title=args.title, year=args.year,
                                                              published_at=args.published_at))
    elif args.group == "import-directory": _print(service.import_directory(
        args.source, args.directory, manifest_path=args.manifest, dry_run=args.dry_run
    ))
    elif args.group == "query":
        if args.entity == "postgraduate": value = repository.search_postgraduate(args.text, args.region, args.year)
        elif args.entity == "undergraduate-majors": value = repository.search_undergraduate(args.text, args.year)
        elif args.entity == "salary": value = repository.search_salary(args.text, args.year)
        elif args.entity == "civil-service": value = repository.search_civil_service(major_text=args.text,
                education=args.education, region=args.region, year=args.year)
        elif args.entity == "shandong-civil-service": value = repository.get_shandong_civil_service_summary(args.year or 2026)
        elif args.entity == "qut-transfer": value = repository.get_qut_policies(args.current_only)
        else:
            if not args.entity_type or args.id is None: raise SystemExit("source-chain requires --entity-type and --id")
            value = repository.get_source_chain(args.entity_type, args.id)
        _print(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
