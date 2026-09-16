"""Add review columns and backfill legacy candidates without confirming them."""
from sqlalchemy import inspect, text


def migrate_study_review(engine):
    table = "study_knowledge_units"
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns(table)}
    timestamp = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "DATETIME"
    columns = {
        "original_content": "TEXT NOT NULL DEFAULT ''",
        "review_status": "VARCHAR(20) NOT NULL DEFAULT 'pending'",
        "confirmed_at": timestamp,
        "updated_at": timestamp,
        "deleted_at": timestamp,
        "version": "INTEGER NOT NULL DEFAULT 1",
    }
    with engine.begin() as conn:
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        if "original_content" not in existing:
            conn.execute(text(f"UPDATE {table} SET original_content = content"))
        conn.execute(text(f"UPDATE {table} SET updated_at = created_at WHERE updated_at IS NULL"))
