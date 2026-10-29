"""Stage 1, ingest: copy every raw portal table into analysis.unified_postings.

Each row gets the portal name (= raw table name) and a deterministic uid.
Idempotent: rows already ingested are skipped, so re-runs are safe.

    uv run python -m jobpipe.ingest
"""

import hashlib
import logging

from sqlalchemy import Connection, create_engine, text

from jobpipe.config import Settings
from jobpipe.raw import portal_tables

log = logging.getLogger(__name__)

UID_LENGTH = 16


def make_uid(portal: str, source_id: int) -> str:
    """Python twin of the SQL expression in INGEST_SQL (kept in sync by tests)."""
    return hashlib.sha256(f"{portal}:{source_id}".encode()).hexdigest()[:UID_LENGTH]


INGEST_SQL = """
INSERT INTO unified_postings
    (uid, portal, source_id, title, url, location, posted, scraped, company, description, job_type)
SELECT
    SUBSTR(SHA2(CONCAT(:portal, ':', r.id), 256), 1, {uid_len}),
    :portal, r.id, r.title, r.url, r.location, r.posted, r.scraped, r.company, r.description,
    r.`type`
FROM `{raw_db}`.`{table}` AS r
WHERE NOT EXISTS (
    SELECT 1 FROM unified_postings AS u WHERE u.portal = :portal AND u.source_id = r.id
)
"""


def ingest(conn: Connection, raw_db: str) -> dict[str, int]:
    """Ingest all portals. `conn` must point at the analysis DB. Returns new rows per portal."""
    tables = portal_tables(conn, schema=raw_db)
    if not tables:
        raise SystemExit(f"No portal tables found in {raw_db}")
    inserted = {}
    for table in tables:
        sql = text(INGEST_SQL.format(raw_db=raw_db, table=table, uid_len=UID_LENGTH))
        inserted[table] = conn.execute(sql, {"portal": table}).rowcount
        log.info("%-20s %6d new rows", table, inserted[table])
    return inserted


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    s = Settings()
    engine = create_engine(s.url(s.analysis_db))
    with engine.begin() as conn:
        inserted = ingest(conn, s.raw_db)
        total = conn.execute(text("SELECT COUNT(*) FROM unified_postings")).scalar_one()
    log.info("ingested %d new rows; unified_postings now has %d", sum(inserted.values()), total)


if __name__ == "__main__":
    main()
