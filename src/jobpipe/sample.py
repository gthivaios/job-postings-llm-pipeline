"""Validate the raw portal tables and write the sample manifest.

Run against your LOCAL container after loading the raw dumps:
    uv run python -m jobpipe.sample

Read-only: the raw data is published exactly as collected.
"""

import json
import logging
from pathlib import Path

from sqlalchemy import Connection, create_engine, text

from jobpipe.config import Settings
from jobpipe.raw import DATE_COLUMN, KEY_COLUMN, portal_tables

log = logging.getLogger(__name__)

MANIFEST_PATH = Path("data/sample_manifest.json")


def check_key(conn: Connection, table: str) -> None:
    """Fail loudly if `id` is not unique; ingest and every later stage rely on it."""
    total, distinct = conn.execute(
        text(f"SELECT COUNT(*), COUNT(DISTINCT `{KEY_COLUMN}`) FROM `{table}`")
    ).one()
    if total != distinct:
        raise ValueError(f"{table}: {total - distinct} duplicate ids")


def build_manifest(conn: Connection, tables: list[str]) -> dict:
    counts, lo, hi = {}, None, None
    for t in tables:
        n, mn, mx = conn.execute(
            text(f"SELECT COUNT(*), MIN(`{DATE_COLUMN}`), MAX(`{DATE_COLUMN}`) FROM `{t}`")
        ).one()
        counts[t] = n
        mn, mx = str(mn)[:10] if mn else None, str(mx)[:10] if mx else None
        lo = min(filter(None, [lo, mn]), default=None)
        hi = max(filter(None, [hi, mx]), default=None)
    return {
        "tables": counts,
        "total_rows": sum(counts.values()),
        "posted_from": lo,
        "posted_to": hi,
    }


def prepare(conn: Connection) -> dict:
    tables = portal_tables(conn)
    if not tables:
        raise SystemExit("No portal tables found. Did you load the raw dumps?")
    for t in tables:
        check_key(conn, t)
    return build_manifest(conn, tables)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    s = Settings()
    with create_engine(s.url(s.raw_db)).connect() as conn:
        manifest = prepare(conn)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", "utf-8")
    for table, n in manifest["tables"].items():
        log.info("%-20s %6d rows", table, n)
    log.info(
        "wrote %s: %d rows, posted %s to %s",
        MANIFEST_PATH,
        manifest["total_rows"],
        manifest["posted_from"],
        manifest["posted_to"],
    )


if __name__ == "__main__":
    main()
