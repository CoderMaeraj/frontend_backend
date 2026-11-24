"""Lightweight, idempotent schema migrations.

`db.create_all()` creates missing tables but never adds columns to tables that already
exist. Each entry below adds one column to an existing database; columns that are already
present are skipped, so running this repeatedly is safe and never touches existing data.

Run automatically on app start-up, or manually with:  flask --app app migrate
"""
from sqlalchemy import inspect, text

from models import db

# (table, column, extra DDL after the column type). The type is taken from the model.
MIGRATIONS = [
    ("mentor", "max_mentees", "NOT NULL DEFAULT 3"),
    ("mentor", "reviewed_at", ""),
    ("mentoring_request", "preferred_slot_id", "REFERENCES mentor_availability(id) ON DELETE SET NULL"),
    ("mentoring_request", "preferred_date", ""),
    ("mentoring_request", "decline_reason", ""),
    ("message", "sender", ""),
    ("session_summary", "title", ""),
]


def upgrade():
    """Add every missing column. Returns the list of "table.column" names that were added."""
    engine = db.engine
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    added = []
    with engine.begin() as conn:
        for table, column, extra in MIGRATIONS:
            if table not in tables:
                continue  # create_all() builds new tables with every column already
            existing = {c["name"] for c in inspector.get_columns(table)}
            if column in existing:
                continue
            col_type = db.metadata.tables[table].c[column].type.compile(dialect=engine.dialect)
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {col_type} {extra}'.strip()))
            added.append(f"{table}.{column}")
    return added
