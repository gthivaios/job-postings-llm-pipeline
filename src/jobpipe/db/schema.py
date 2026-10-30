"""Analysis DB schema. Alembic migrations in migrations/ must match this."""

from sqlalchemy import (
    CHAR,
    Column,
    DateTime,
    Float,
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
    Column("posted", String(128)),  # as published; free text on some portals ("Πριν 3 ώρες")
    Column("scraped", DateTime),  # collection time: the date used for filtering and windows
    Column("company", String(256)),
    Column("description", Text),
    Column("job_type", String(64)),
    Column("ingested_at", DateTime, nullable=False, server_default=func.now()),
    # Stage 2: translation (NULL = not translated yet)
    Column("en_title", String(512)),
    Column("en_job_type", String(256)),
    Column("en_description", Text),  # en_title + en_job_type + translated description
    Column("translation_model", String(128)),
    Column("translated_at", DateTime),
    Column("translation_cost_usd", Float),
    Column("translation_latency_ms", Integer),
    UniqueConstraint("portal", "source_id", name="uq_portal_source"),
    Index("ix_unified_scraped", "scraped"),
)

# Cache of LLM responses, keyed by sha256(model | prompt version | input text).
# Identical inputs (e.g. the same job type on thousands of postings) are paid for once,
# and re-runs after a crash cost nothing.
llm_cache = Table(
    "llm_cache",
    metadata,
    Column("cache_key", CHAR(64), primary_key=True),
    Column("model", String(128), nullable=False),
    Column("response", Text, nullable=False),
    Column("prompt_tokens", Integer),
    Column("completion_tokens", Integer),
    Column("cost_usd", Float),
    Column("latency_ms", Integer),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
)
