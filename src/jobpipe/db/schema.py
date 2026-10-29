"""Analysis DB schema. Alembic migrations in migrations/ must match this."""

from sqlalchemy import (
    CHAR,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)

metadata = MetaData()

unified_postings = Table(
    "unified_postings",
    metadata,
    # Deterministic key: first 16 hex chars of sha256("<portal>:<source_id>").
    # Same posting -> same uid on every rebuild, so eval sets and traces can reference it.
    Column("uid", CHAR(16), primary_key=True),
    Column("portal", String(64), nullable=False),
    Column("source_id", Integer, nullable=False),
    Column("title", String(256), nullable=False),
    Column("url", String(512), nullable=False),
    Column("location", String(256)),
    Column("posted", DateTime),
    Column("scraped", DateTime),
    Column("company", String(256)),
    Column("description", Text),
    Column("job_type", String(64)),
    Column("ingested_at", DateTime, nullable=False, server_default=func.now()),
    UniqueConstraint("portal", "source_id", name="uq_portal_source"),
    Index("ix_unified_posted", "posted"),
)
